"""The AI's searchable chunks live in Postgres (pgvector), so they survive restarts (see vectorstore.py).

The store logic is tested against a real Postgres when the dev-only `pgserver` package is installed
(pip install pgserver); without it those tests are skipped. The choosing/fallback logic needs nothing."""
import types

import pytest

import database
import vectorstore


class FakeEmbeddings:
    def __init__(self):
        self.queries = {}

    def embed_query(self, text):
        return self.queries[text]


def _postgres_engine(monkeypatch):
    return types.SimpleNamespace(dialect=types.SimpleNamespace(name="postgresql"))


def test_sqlite_uses_the_on_disk_index():
    store = vectorstore.make_store(FakeEmbeddings(), object())
    assert store.name == "chroma" and store.persistent is False


def test_postgres_with_pgvector_uses_the_database(monkeypatch):
    monkeypatch.setattr(database, "engine", _postgres_engine(monkeypatch))
    monkeypatch.setattr(vectorstore.PgVectorStore, "ensure_schema", lambda self: None)
    store = vectorstore.make_store(FakeEmbeddings(), object())
    assert store.name == "pgvector" and store.persistent is True


def test_postgres_without_pgvector_falls_back_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(database, "engine", _postgres_engine(monkeypatch))

    def no_pgvector(self):
        raise RuntimeError('type "vector" does not exist')
    monkeypatch.setattr(vectorstore.PgVectorStore, "ensure_schema", no_pgvector)
    assert vectorstore.make_store(FakeEmbeddings(), object()).name == "chroma"


def test_the_old_index_can_be_forced_back_on(monkeypatch):
    monkeypatch.setattr(database, "engine", _postgres_engine(monkeypatch))
    monkeypatch.setattr(vectorstore.config, "VECTOR_BACKEND", "chroma", raising=False)
    assert vectorstore.make_store(FakeEmbeddings(), object()).name == "chroma"


# ---------------------------------------------------------------- against a real Postgres
pgserver = pytest.importorskip("pgserver", reason="pip install pgserver to run the pgvector tests")
np = pytest.importorskip("numpy")
from sqlalchemy import create_engine  # noqa: E402

DIM = 64


def _unit(vector):
    return (vector / np.linalg.norm(vector)).tolist()


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    server = pgserver.get_server(tmp_path_factory.mktemp("pg"))
    engine = create_engine(server.get_uri().replace("postgresql://", "postgresql+psycopg2://"))
    yield engine
    engine.dispose()
    server.cleanup()


@pytest.fixture
def store(pg):
    emb = FakeEmbeddings()
    s = vectorstore.PgVectorStore(pg, emb)
    s.ensure_schema()
    s.clear()
    return s


def _load(store, count=30, seed=3):
    rng = np.random.default_rng(seed)
    vectors = [_unit(rng.normal(size=DIM)) for _ in range(count)]
    metas = [{"source": f"s{i % 3}", "page": i, "branch": "A" if i % 2 else "B", "type": "uploaded_material"} for i in range(count)]
    store.upsert([f"id{i}" for i in range(count)], [f"chunk {i}" for i in range(count)], metas, vectors)
    return vectors, metas


def test_search_matches_plain_maths_with_and_without_filters(store):
    vectors, metas = _load(store)
    query = _unit(np.array(vectors[5]) + 0.05)
    store.embeddings.queries["q"] = query
    for where in (None, {"source": "s2"}, {"branch": "A"}):
        got = store.search("q", 5, where)
        truth = sorted((np.linalg.norm(np.array(vectors[i]) - np.array(query)) ** 2, f"chunk {i}")
                       for i in range(len(vectors)) if not where or all(metas[i][k] == v for k, v in where.items()))[:5]
        assert [doc.page_content for doc, _ in got] == [name for _, name in truth]
        assert [round(d, 4) for _, d in got] == [round(d, 4) for d, _ in truth]   # squared L2, like the old index


def test_chunks_survive_a_restart_and_are_not_embedded_again(pg, store):
    _load(store)
    after_restart = vectorstore.PgVectorStore(pg, FakeEmbeddings())   # a new process = a new store object
    assert after_restart.has_source("s1") and not after_restart.has_source("nope")


def test_upserting_the_same_ids_replaces_instead_of_duplicating(store):
    _load(store)
    _load(store)
    assert len(store.chunks_for_source("s0")) == 10


def test_removing_unwanted_files_never_wipes_everything_on_an_empty_list(store):
    _load(store)
    assert store.delete_sources_not_in(set()) == 0
    assert store.delete_sources_not_in({"s1"}) == 20 and store.has_source("s1") and not store.has_source("s0")


def test_delete_clear_and_page_lookup(store):
    _load(store)
    assert sorted(page for page, _ in store.chunks_for_source("s1"))[:3] == [1, 4, 7]
    assert store.delete_source("s1") == 10
    assert len(store.managed_ids()) == 20
    store.delete_ids(store.managed_ids()[:5])
    assert len(store.managed_ids()) == 15
    assert store.clear() == 15 and store.managed_ids() == []


def test_nul_bytes_from_pdf_text_do_not_break_saving(store):
    store.upsert(["nul"], ["bad\x00text"], [{"source": "z", "page": 1, "branch": "A"}], [_unit(np.ones(DIM))])
    assert store.chunks_for_source("z")[0][1] == "badtext"
