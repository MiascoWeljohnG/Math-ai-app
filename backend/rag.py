import asyncio
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
    """Raised when a request waits too long for Ollama to respond."""

def extract_text(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return path.read_text(encoding="utf-8")

    elif suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n\n"
        return text

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
        return text

    else:
        return ""


def ingest_documents(file_paths: list[str]):
    docs = []
    for fp in file_paths:
        text = extract_text(fp)
        if text.strip():
            docs.append({"text": text, "source": Path(fp).name})

    if not docs:
        return

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    all_chunks = []
    all_sources = []
    for doc in docs:
        chunks = splitter.split_text(doc["text"])
        all_chunks.extend(chunks)
        all_sources.extend([doc["source"]] * len(chunks))

    if not all_chunks:
        return

    vector_store = Chroma(
        collection_name=config.CHROMA_COLLECTION,
        embedding_function=embeddings,
        client=chroma_client,
    )
    vector_store.add_texts(texts=all_chunks, metadatas=[{"source": s} for s in all_sources])


async def ask(question: str, chat_history: list[dict] = None) -> dict:
    """
    Runs one chat turn against Ollama. Returns a dict with the answer plus
    how long the request had to wait behind other students, so the caller
    can surface that to the UI instead of just showing bouncing dots forever.
    """
    # similarity_search does its own blocking HTTP call to Ollama for the
    # query embedding — keep it off the event loop.
    results = await asyncio.to_thread(_similarity_search, question)
    context = "\n\n".join([doc.page_content for doc in results]) if results else ""

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
        "Use the provided reference material if it's relevant to the question. "
        "If you don't know the answer, say so honestly."
    )
    if context:
        system_prompt += f"\n\nReference material (use if relevant):\n{context}"

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
        try:
            response = await asyncio.wait_for(
                _async_ollama_client.chat(model=config.OLLAMA_MODEL, messages=messages),
                timeout=config.OLLAMA_CHAT_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise QueueTimeoutError(
                "The AI is taking longer than usual to respond. Please try again."
            )

    return {
        "answer": response["message"]["content"],
        "was_queued": queue_position > 1,
        "queue_position": queue_position,
    }


def queue_status() -> dict:
    """Lightweight snapshot for the frontend to poll while a student waits."""
    return {"waiting": _waiting_count, "max_concurrent": config.MAX_CONCURRENT_CHATS}


def _similarity_search(question: str):
    vector_store = Chroma(
        collection_name=config.CHROMA_COLLECTION,
        embedding_function=embeddings,
        client=chroma_client,
    )
    return vector_store.similarity_search(question, k=3)