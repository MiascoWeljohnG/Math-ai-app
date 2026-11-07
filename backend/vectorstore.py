"""Where the AI's searchable chunks are kept.

PgVectorStore keeps them in the app's own Postgres database (Supabase) with the pgvector extension, so they
survive Render restarts, sleeping and redeploys: a file is embedded ONCE, ever. ChromaStore is the old
on-disk index. It is wiped whenever Render restarts, which forced every file to be embedded again each time.
It stays as the fallback for SQLite (local development) and for a Postgres without pgvector.

Set VECTOR_BACKEND=chroma to switch back to the old index at any time ("auto" is the default).

Both stores answer the same questions, so rag.py doesn't care which one it has:
    upsert / has_source / delete_source / delete_sources_not_in / managed_ids / delete_ids /
    chunks_for_source / search / clear
"""
import logging

from langchain_core.documents import Document
from sqlalchemy import bindparam, text

import config

log = logging.getLogger(__name__)

MANAGED_TYPES = ("obsidian_note", "uploaded_material")
_BATCH = 100   # rows per INSERT round trip


def _vector_literal(vector) -> str:
    """pgvector's text form of a vector: [0.1,0.2,...] (float32 precision is plenty)."""
    return "[" + ",".join(format(float(x), ".8g") for x in vector) + "]"


class PgVectorStore:
    name = "pgvector"
    persistent = True   # survives restarts, so files already embedded never need embedding again

    def __init__(self, engine, embeddings):
        self.engine = engine
        self.embeddings = embeddings

    def ensure_schema(self) -> None:
        """Create the extension and the table if they aren't there yet. Raises if the database can't do it."""
        try:
            with self.engine.begin() as conn:   # its own transaction: a refusal must not spoil the next steps
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception as exc:
            log.warning("Couldn't run CREATE EXTENSION vector (%s); carrying on in case it is already enabled", exc)
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS material_chunks (
                    id        TEXT PRIMARY KEY,
                    source    TEXT NOT NULL,
                    page      INTEGER,
                    branch    TEXT,
                    type      TEXT NOT NULL DEFAULT 'uploaded_material',
                    content   TEXT NOT NULL,
                    embedding vector NOT NULL
                )"""))
            conn.execute(text("CREATE INDEX IF NOT EXISTS material_chunks_source_idx ON material_chunks (source)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS material_chunks_branch_idx ON material_chunks (branch)"))
            # No vector index on purpose: a school's worth of chunks is a few thousand rows, which an exact
            # scan searches in milliseconds, and it keeps results identical to the old index.

    # ---- writing
    def upsert(self, ids, documents, metadatas, embeddings) -> None:
        rows = [{
            "id": chunk_id,
            "source": meta.get("source", ""),
            "page": meta.get("page"),
            "branch": meta.get("branch"),
            "type": meta.get("type", "uploaded_material"),
            "content": document.replace("\x00", ""),   # Postgres text can't hold NUL bytes (PDFs sometimes do)
            "embedding": _vector_literal(vector),
        } for chunk_id, document, meta, vector in zip(ids, documents, metadatas, embeddings)]
        statement = text("""
            INSERT INTO material_chunks (id, source, page, branch, type, content, embedding)
            VALUES (:id, :source, :page, :branch, :type, :content, CAST(:embedding AS vector))
            ON CONFLICT (id) DO UPDATE SET source = EXCLUDED.source, page = EXCLUDED.page,
                branch = EXCLUDED.branch, type = EXCLUDED.type, content = EXCLUDED.content,
                embedding = EXCLUDED.embedding""")
        with self.engine.begin() as conn:   # one transaction: a file's chunks arrive together or not at all
            for start in range(0, len(rows), _BATCH):
                conn.execute(statement, rows[start:start + _BATCH])

    # ---- reading / deleting
    def has_source(self, source: str) -> bool:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT 1 FROM material_chunks WHERE source = :s LIMIT 1"), {"s": source}).first() is not None

    def delete_source(self, source: str) -> int:
        with self.engine.begin() as conn:
            return conn.execute(text("DELETE FROM material_chunks WHERE source = :s"), {"s": source}).rowcount

    def delete_sources_not_in(self, sources: set[str]) -> int:
        """Drop the uploaded-material chunks of every file that is no longer wanted."""
        if not sources:   # never wipe everything because a list came back empty
            return 0
        statement = text("DELETE FROM material_chunks WHERE type = 'uploaded_material' AND source NOT IN :sources")
        with self.engine.begin() as conn:
            return conn.execute(statement.bindparams(bindparam("sources", expanding=True)), {"sources": sorted(sources)}).rowcount

    def managed_ids(self) -> list[str]:
        statement = text("SELECT id FROM material_chunks WHERE type IN :types").bindparams(bindparam("types", expanding=True))
        with self.engine.connect() as conn:
            return [row[0] for row in conn.execute(statement, {"types": list(MANAGED_TYPES)})]

    def delete_ids(self, ids) -> None:
        ids = list(ids)
        statement = text("DELETE FROM material_chunks WHERE id IN :ids").bindparams(bindparam("ids", expanding=True))
        with self.engine.begin() as conn:
            for start in range(0, len(ids), 500):
                conn.execute(statement, {"ids": ids[start:start + 500]})

    def chunks_for_source(self, source: str) -> list[tuple]:
        with self.engine.connect() as conn:
            return [(row[0], row[1]) for row in conn.execute(
                text("SELECT page, content FROM material_chunks WHERE source = :s"), {"s": source})]

    def clear(self) -> int:
        with self.engine.begin() as conn:
            return conn.execute(text("DELETE FROM material_chunks WHERE type = 'uploaded_material'")).rowcount

    # ---- searching
    def search(self, question: str, k: int, where: dict | None = None) -> list[tuple[Document, float]]:
        """The k chunks closest to the question, as (Document, distance). The distance is the SQUARED L2
        distance, the same measure the old index used, so MAX_CONTEXT_DISTANCE keeps its meaning."""
        query = _vector_literal(self.embeddings.embed_query(question))   # before borrowing a connection
        filters, params = [], {"q": query, "k": k}
        for column in ("source", "branch"):
            if where and column in where:
                filters.append(f"{column} = :{column}")
                params[column] = where[column]
        clause = ("WHERE " + " AND ".join(filters)) if filters else ""
        statement = text(f"""
            SELECT content, source, page, branch, type, embedding <-> CAST(:q AS vector) AS distance
            FROM material_chunks {clause}
            ORDER BY embedding <-> CAST(:q AS vector)
            LIMIT :k""")
        with self.engine.connect() as conn:
            rows = conn.execute(statement, params).all()
        return [(Document(page_content=row[0], metadata={"source": row[1], "page": row[2], "branch": row[3], "type": row[4]}),
                 float(row[5]) ** 2) for row in rows]


class ChromaStore:
    name = "chroma"
    persistent = False   # on Render's disk: gone after every restart, so everything is embedded again

    def __init__(self, client, collection_name, embeddings):
        self.client = client
        self.collection_name = collection_name
        self.embeddings = embeddings

    def _collection(self):
        return self.client.get_or_create_collection(name=self.collection_name)

    def upsert(self, ids, documents, metadatas, embeddings) -> None:
        self._collection().upsert(documents=documents, metadatas=metadatas, ids=ids, embeddings=embeddings)

    def has_source(self, source: str) -> bool:
        return bool(self._collection().get(where={"source": source}, limit=1)["ids"])

    def delete_source(self, source: str) -> int:
        collection = self._collection()
        ids = collection.get(where={"source": source})["ids"]
        if ids:
            collection.delete(ids=ids)
        return len(ids)

    def delete_sources_not_in(self, sources: set[str]) -> int:
        collection = self._collection()
        existing = collection.get(where={"type": "uploaded_material"}, include=["metadatas"])
        stale = [chunk_id for chunk_id, meta in zip(existing["ids"], existing["metadatas"])
                 if (meta or {}).get("source") not in sources]
        if stale:
            collection.delete(ids=stale)
        return len(stale)

    def managed_ids(self) -> list[str]:
        existing = self._collection().get(include=["metadatas"])
        return [chunk_id for chunk_id, meta in zip(existing["ids"], existing["metadatas"])
                if (meta or {}).get("type") in MANAGED_TYPES]

    def delete_ids(self, ids) -> None:
        ids = list(ids)
        if ids:
            self._collection().delete(ids=ids)

    def chunks_for_source(self, source: str) -> list[tuple]:
        got = self._collection().get(where={"source": source}, include=["documents", "metadatas"])
        return [((meta or {}).get("page"), document) for document, meta in zip(got["documents"], got["metadatas"])]

    def clear(self) -> int:
        collection = self._collection()
        ids = collection.get(where={"type": "uploaded_material"}, include=["metadatas"])["ids"]
        if ids:
            collection.delete(ids=ids)
        return len(ids)

    def search(self, question: str, k: int, where: dict | None = None) -> list[tuple[Document, float]]:
        from langchain_community.vectorstores import Chroma
        store = Chroma(collection_name=self.collection_name, embedding_function=self.embeddings, client=self.client)
        kwargs = {"filter": where} if where else {}
        return store.similarity_search_with_score(question, k=k, **kwargs)


def make_store(embeddings, chroma_client):
    """Pick the store: pgvector when the app runs on Postgres and the extension works, else the old Chroma index.
    A Postgres that can't do pgvector must never take the app down, so that case falls back (loudly)."""
    backend = getattr(config, "VECTOR_BACKEND", "auto").lower()
    if backend != "chroma":
        from database import engine
        if engine.dialect.name == "postgresql":
            store = PgVectorStore(engine, embeddings)
            try:
                store.ensure_schema()
                log.info("Search index: pgvector in the Postgres database (survives restarts)")
                return store
            except Exception as exc:
                log.error("pgvector isn't available (%s). Using the temporary on-disk index, which is wiped on every "
                          "restart. Fix: in the Supabase SQL editor run  create extension if not exists vector;", exc)
        elif backend == "pgvector":
            log.warning("VECTOR_BACKEND=pgvector needs a PostgreSQL DATABASE_URL; using the on-disk index instead")
    log.info("Search index: on-disk Chroma (wiped whenever the server restarts)")
    if callable(chroma_client):   # rag.py passes a getter so Chroma is only imported when it is really used
        chroma_client = chroma_client()
    return ChromaStore(chroma_client, config.CHROMA_VAULT_COLLECTION, embeddings)
