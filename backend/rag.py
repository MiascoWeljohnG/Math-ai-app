import asyncio
import re
import chromadb
import ollama
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma

import config

chroma_client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
collection = chroma_client.get_or_create_collection(name=config.CHROMA_COLLECTION)

embeddings = OllamaEmbeddings(model="nomic-embed-text", base_url=config.OLLAMA_BASE_URL)

# Async client so /ask no longer blocks the event loop while waiting on Ollama.
_async_ollama_client = ollama.AsyncClient(host=config.OLLAMA_BASE_URL)

# Caps how many generations run against Ollama at once (see config.py).
_chat_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_CHATS)
# Tracks how many requests are currently waiting for a free slot, so we can
# tell a student "you're 2nd in line" instead of leaving them guessing.
_waiting_count = 0
_waiting_lock = asyncio.Lock()


class QueueTimeoutError(Exception):
    """Deprecated: no longer raised. Kept only so older imports don't break;
    safe to ignore."""

def extract_text_by_page(file_path: str) -> list[tuple[int, str]]:
    """Returns [(page_number, text), ...]. PDFs keep real 1-indexed page
    numbers so chunks can be traced back to a page; .txt/.docx have no page
    concept, so they come back as a single (0, text) entry."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text and page_text.strip():
                pages.append((i, page_text))
        return pages

    elif suffix == ".txt":
        return [(0, path.read_text(encoding="utf-8"))]

    elif suffix == ".docx":
        from docx import Document
        doc = Document(path)
        text = ""
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text += paragraph.text + "\n"
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        text += cell.text + "\n"
        return [(0, text)]

    return []


def ingest_documents(file_paths: list[str], branch: str = "General"):
    """Chunks each file page by page (so every chunk knows which page it came
    from) and tags every chunk with its source filename, page and math
    branch. Note: because chunking now happens per page, a passage that
    straddles a page break becomes two chunks instead of one overlapping one."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    all_chunks = []
    all_metadatas = []
    for fp in file_paths:
        source = Path(fp).name
        for page_num, page_text in extract_text_by_page(fp):
            if not page_text.strip():
                continue
            for chunk in splitter.split_text(page_text):
                all_chunks.append(chunk)
                all_metadatas.append({"source": source, "page": page_num, "branch": branch})

    if not all_chunks:
        return

    vector_store = Chroma(
        collection_name=config.CHROMA_COLLECTION,
        embedding_function=embeddings,
        client=chroma_client,
    )
    vector_store.add_texts(texts=all_chunks, metadatas=all_metadatas)


_PAGE_RE = re.compile(r"pages?\s*(\d+)(?:\s*(?:-|–|to|and)\s*(\d+))?", re.IGNORECASE)


def _page_request(question: str):
    """If the question names specific page(s) ("page 6", "pages 6-7"),
    return (start, end); otherwise None. Semantic search can't answer these
    — the words "page 6" don't resemble the content on page 6 — so they get
    a direct lookup by page metadata instead."""
    m = _PAGE_RE.search(question)
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else start
    if end < start:
        start, end = end, start
    return (start, end)


def _chunks_for_pages(filename: str, start: int, end: int, limit: int = 8):
    vector_store = Chroma(
        collection_name=config.CHROMA_COLLECTION,
        embedding_function=embeddings,
        client=chroma_client,
    )
    got = vector_store._collection.get(where={"source": filename}, include=["documents", "metadatas"])
    matches = []
    for text, meta in zip(got["documents"], got["metadatas"]):
        page = (meta or {}).get("page")
        if page is not None and start <= page <= end:
            matches.append((page, text))
    matches.sort(key=lambda t: t[0])
    return matches[:limit]


async def ask(question: str, chat_history: list[dict] = None, material_filename: str = None) -> dict:
    """
    Runs one chat turn against Ollama. `material_filename`, when given, is the
    document the student currently has open in the materials viewer: retrieval
    is then limited to that file (and "page 6-7" style questions are answered
    from those exact pages), instead of searching the whole knowledge base.
    """
    context = ""
    if material_filename:
        page_range = _page_request(question)
        if page_range:
            page_chunks = await asyncio.to_thread(_chunks_for_pages, material_filename, *page_range)
            context = "\n\n".join(f"[Page {p}] {t}" for p, t in page_chunks)
        else:
            results = await asyncio.to_thread(_similarity_search, question, material_filename)
            context = "\n\n".join(
                f"[Page {d.metadata.get('page', '?')}] {d.page_content}" for d in results
            )
    else:
        # similarity_search does its own blocking HTTP call to Ollama for the
        # query embedding — keep it off the event loop.
        results = await asyncio.to_thread(_similarity_search, question)
        context = "\n\n".join(d.page_content for d in results) if results else ""

    system_prompt = (
        "You are a friendly math assistant for students. "
        "You can have normal conversation — greetings, small talk, thanking you, "
        "asking who/what you are — respond naturally and briefly to those. "
        "For anything that is actually a question or request for help, ONLY help if "
        "it is related to mathematics (arithmetic, algebra, geometry, statistics, "
        "calculus, etc.). If someone asks for substantive help on a non-math topic "
        "(history, coding, writing, other homework, etc.), politely decline and say: "
        "'I can only help with math questions. Please ask me something related to mathematics.' "
        "For math problems, show your work step by step. "
        "Be clear, concise, and structured in your explanations. "
        "If reference material is provided below, it comes from course documents "
        "your instructor uploaded to a shared knowledge base for THIS question only — "
        "it is not something you said earlier, and you have no memory of using or not "
        "using it on any previous turn. Use it only if it genuinely helps answer the "
        "current question; if it doesn't, ignore it silently and never apologize for "
        "'not referencing' something from a prior answer. "
        "If you don't know the answer, say so honestly."
    )
    if material_filename:
        display = re.sub(r"^[a-f0-9]{32}_", "", material_filename, flags=re.IGNORECASE)
        system_prompt += (
            f"\n\nThe student currently has the document \"{display}\" open and is asking about it. "
            "The excerpts below are taken only from that document, labelled with their page numbers; "
            "when you use them, mention the page. If the excerpts don't contain what the student "
            "asks about, say you couldn't find it in the parts of the document you can see, "
            "rather than guessing."
        )
        if context:
            system_prompt += f"\n\nExcerpts from the open document:\n{context}"
        else:
            system_prompt += "\n\n(No excerpts from the open document matched this question.)"
    elif context:
        system_prompt += f"\n\nReference material for this question only (use if relevant, otherwise ignore):\n{context}"

    messages = [{"role": "system", "content": system_prompt}]

    if chat_history:
        for msg in chat_history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": question})

    global _waiting_count
    async with _waiting_lock:
        _waiting_count += 1
        queue_position = _waiting_count

    async with _chat_semaphore:
        async with _waiting_lock:
            _waiting_count -= 1
        # No timeout here by design — a slow local model finishing late is
        # better than cutting a student off mid-answer. The semaphore above
        # is what actually protects the server from being overwhelmed; this
        # just lets a single generation take as long as it needs.
        response = await _async_ollama_client.chat(model=config.OLLAMA_MODEL, messages=messages)

    return {
        "answer": response["message"]["content"],
        "was_queued": queue_position > 1,
        "queue_position": queue_position,
    }


def queue_status() -> dict:
    """Lightweight snapshot for the frontend to poll while a student waits."""
    return {"waiting": _waiting_count, "max_concurrent": config.MAX_CONCURRENT_CHATS}


def _similarity_search(question: str, source_filter: str = None):
    vector_store = Chroma(
        collection_name=config.CHROMA_COLLECTION,
        embedding_function=embeddings,
        client=chroma_client,
    )
    # similarity_search_with_score always returns the top k nearest chunks,
    # even when none are actually relevant, so results farther than
    # MAX_CONTEXT_DISTANCE are dropped (see config.py for tuning). When
    # source_filter is set, only chunks from that one file are considered.
    kwargs = {"filter": {"source": source_filter}} if source_filter else {}
    k = 5 if source_filter else 3
    results = vector_store.similarity_search_with_score(question, k=k, **kwargs)
    return [doc for doc, distance in results if distance <= config.MAX_CONTEXT_DISTANCE]
