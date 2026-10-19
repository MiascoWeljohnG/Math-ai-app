"""Tests run without Ollama/Chroma: `rag` is replaced by a small fake whose model replies are
whatever the test sets in `fake_rag.reply`."""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

fake_rag = types.ModuleType("rag")
fake_rag.reply = ""            # what the "model" answers next (str, Exception, or a list of them, one per call)
fake_rag.ingested = []         # (branch, [file names]) for every ingest call


async def generate_text(system, prompt, branch, query):
    reply = fake_rag.reply.pop(0) if isinstance(fake_rag.reply, list) else fake_rag.reply   # a list = one reply per call
    if isinstance(reply, Exception):
        raise reply
    return reply


def extract_text_from_bytes(filename, contents):
    text = contents.decode("utf-8", errors="ignore")
    return [(0, text, [])] if text.strip() else []


def ingest_uploaded_materials(files, branch="General", storage_ids=None):
    fake_rag.ingested.append((branch, [name for name, _ in files]))
    return [f"Uploaded Materials/{branch}/id_{name}" for name, _ in files]


async def ask_stream(*args, **kwargs):  # imported by subjects_routes, unused here
    yield {"type": "done", "answer": ""}


fake_rag.generate_text = generate_text
fake_rag.extract_text_from_bytes = extract_text_from_bytes
fake_rag.ingest_uploaded_materials = ingest_uploaded_materials
fake_rag.ask_stream = ask_stream
fake_rag.ingest_uploads = lambda *args, **kwargs: 0   # imported by materials_routes, unused here
sys.modules["rag"] = fake_rag


@pytest.fixture
def rag():
    fake_rag.reply = ""
    fake_rag.ingested.clear()
    return fake_rag


@pytest.fixture
def db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    import models  # noqa: F401  (registers the tables)
    from database import Base
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
