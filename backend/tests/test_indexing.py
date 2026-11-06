"""Uploads are saved at once and read by the AI in the background (indexing.py)."""
from datetime import datetime

import pytest
from sqlalchemy.orm import sessionmaker

import indexing
from models import Material
from routes.materials_routes import material_summary
from tests.test_classifier import STATS, run_upload


@pytest.fixture
def jobs(db, monkeypatch, rag):
    """Run indexing jobs on the test database and let tests see what the fake AI was asked to do."""
    monkeypatch.setattr(indexing, "SessionLocal", sessionmaker(bind=db.get_bind()))
    rag.deleted_chunks.clear()
    return rag


def add_material(db, **fields):
    row = Material(filename="Uploaded Materials/Algebra/id_a.pdf", display_name="a.pdf", branch="Algebra",
                   uploaded_by="teacher1", **fields)
    db.add(row)
    db.commit()
    return row


def test_upload_saves_the_row_at_once_and_queues_indexing(rag, db, no_background_indexing):
    rag.reply = STATS
    out = run_upload(db, [("probability.pdf", b"random variables")])
    row = db.query(Material).one()
    assert row.index_status == "indexing"          # visible in the list right away
    assert no_background_indexing == [row.id]      # the slow part was queued, not done in the request
    assert "background" in out["message"]


def test_successful_indexing_marks_the_file_ready(db, jobs):
    row = add_material(db, index_status="indexing")
    indexing._index(row.id, b"bytes")
    db.refresh(row)
    assert row.index_status == "ready" and row.index_error is None


def test_failed_indexing_is_recorded_with_a_reason(db, jobs):
    row = add_material(db, index_status="indexing")

    def boom(source, branch, contents):
        raise ValueError("No readable text found in a.pdf.")
    jobs.index_document = boom
    indexing._index(row.id, b"bytes")
    db.refresh(row)
    assert row.index_status == "failed" and "No readable text" in row.index_error


def test_quota_error_keeps_its_plain_language_advice(db, jobs):
    class EmbeddingQuotaError(RuntimeError):
        pass
    row = add_material(db, index_status="indexing")

    def over_quota(source, branch, contents):
        raise EmbeddingQuotaError("Wait a minute and try again with fewer files at a time.")
    jobs.index_document = over_quota
    indexing._index(row.id, b"bytes")
    db.refresh(row)
    assert row.index_status == "failed" and row.index_error.startswith("Wait a minute")


def test_file_deleted_while_indexing_leaves_no_chunks_behind(db, jobs):
    row = add_material(db, index_status="indexing")
    source = row.filename

    def delete_then_finish(src, branch, contents):
        other = indexing.SessionLocal()
        other.query(Material).delete()
        other.commit()
        other.close()
        return 3
    jobs.index_document = delete_then_finish
    indexing._index(row.id, b"bytes")
    assert jobs.deleted_chunks == [source]


def test_retry_puts_a_failed_file_back_in_the_queue(db, no_background_indexing):
    row = add_material(db, index_status="failed", index_error="old reason")
    indexing.retry(row, db)
    db.refresh(row)
    assert row.index_status == "indexing" and row.index_error is None
    assert no_background_indexing == [row.id]


def test_restart_requeues_files_that_were_being_read(db, jobs, no_background_indexing):
    long_ago = datetime(2000, 1, 1)
    lost = add_material(db, index_status="indexing", uploaded_at=long_ago)
    done = Material(filename="Uploaded Materials/Algebra/id_b.pdf", display_name="b.pdf", branch="Algebra",
                    uploaded_by="teacher1", index_status="ready", uploaded_at=long_ago)
    fresh = Material(filename="Uploaded Materials/Algebra/id_c.pdf", display_name="c.pdf", branch="Algebra",
                     uploaded_by="teacher1", index_status="indexing")   # uploaded after this start: not ours
    db.add_all([done, fresh])
    db.commit()
    indexing.resume_stale_jobs()
    assert no_background_indexing == [lost.id]   # only the interrupted one is picked up again


def test_a_job_that_runs_out_of_time_fails_with_a_clear_message(db, jobs):
    row = add_material(db, index_status="indexing")

    def too_slow(source, branch, contents):
        raise TimeoutError("Reading this file took too long and was stopped. Press Retry to try again.")
    jobs.index_document = too_slow
    indexing._index(row.id, b"bytes")
    db.refresh(row)
    assert row.index_status == "failed" and "took too long" in row.index_error


def test_old_rows_without_a_status_count_as_ready(db):
    row = add_material(db)
    row.index_status = None
    assert material_summary(row)["index_status"] == "ready"
