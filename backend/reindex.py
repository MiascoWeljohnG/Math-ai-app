"""Re-index uploaded files into the search index (the `material_chunks` table in Supabase), a few pages at a time.

Run it from the backend folder, on a computer with enough RAM (your laptop), with backend/.env holding the same
DATABASE_URL, Google Drive and Gemini settings as Render. Each file is read PDF_BATCH_PAGES pages at a time (10 by
default); every batch is chunked, embedded and saved before the next one is read, so chunks appear in Supabase as
the file is worked through.

    python tools/reindex.py                  re-index every file
    python tools/reindex.py "Week 1"         only files whose name contains "Week 1"
    python tools/reindex.py --missing        only files that have no chunks yet
    python tools/reindex.py --list           show each file and how many chunks it has; changes nothing

A re-indexed file's old chunks are replaced. If a file fails part-way its chunks are removed again, and the page
shows it as failed with a Retry button. If Gemini's daily quota runs out the run stops (finished files stay finished).
Gemini's free tier embeds about 25,000 tokens a minute, so a big batch of files takes a while: that is normal.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import config  # noqa: E402  (also loads .env)
import indexing  # noqa: E402
import rag  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import Material  # noqa: E402


def _set_status(material_id: int, status: str, error: str | None) -> None:
    """Update the file's row quietly (no notification to the teacher: this is a maintenance run)."""
    db = SessionLocal()
    try:
        material = db.query(Material).filter(Material.id == material_id).first()
        if material is not None:
            material.index_status, material.index_error = status, error
            db.commit()
    finally:
        db.close()


def _progress_printer(info: dict) -> None:
    phase = info.get("phase")
    if phase == "embedding":
        print(f"\r    page {info.get('done')} of {info.get('total')}   ", end="", flush=True)
    elif phase == "waiting":
        print(f"\r    waiting {info.get('seconds')}s for the embedding rate limit...   ", end="", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Re-index uploaded files, a few pages at a time.")
    parser.add_argument("name", nargs="?", default="", help="only files whose name contains this text")
    parser.add_argument("--missing", action="store_true", help="only files that have no chunks yet")
    parser.add_argument("--list", action="store_true", help="list the files and their chunk counts, change nothing")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        rows = [(m.id, m.filename, m.display_name, m.branch or "General", m.drive_file_id, m.school_id)
                for m in db.query(Material).order_by(Material.id).all()]
    finally:
        db.close()

    needle = args.name.lower()
    rows = [row for row in rows if needle in row[1].lower() or needle in (row[2] or "").lower()]
    counts = {row[0]: len(rag.store.chunks_for_source(rag._material_index_source(row[1]))) for row in rows}
    if args.missing:
        rows = [row for row in rows if counts[row[0]] == 0]
    if not rows:
        print("No matching files.")
        return 0

    if args.list:
        for material_id, filename, display_name, branch, _, _ in rows:
            print(f"{counts[material_id]:>5} chunks  [{branch}]  {display_name or filename}")
        print(f"\n{len(rows)} file(s), {sum(counts[row[0]] for row in rows)} chunks.")
        return 0

    print(f"Re-indexing {len(rows)} file(s), {config.PDF_BATCH_PAGES} pages at a time.\n")
    done = failed = total_chunks = 0
    rag.set_job_deadline(None)   # no time limit here: a big file can wait out the embedding rate limit
    rag.set_job_progress(_progress_printer)
    try:
        for number, (material_id, filename, display_name, branch, drive_file_id, school_id) in enumerate(rows, 1):
            print(f"[{number}/{len(rows)}] {display_name or filename}")
            started = time.time()
            try:
                data = indexing._load_bytes(filename, drive_file_id)
                chunks = rag.index_document(filename, branch, data, school_id)
            except rag.EmbeddingQuotaError as exc:
                print(f"\n    stopped: {exc}")
                _set_status(material_id, indexing.FAILED, indexing._explain(exc))
                failed += 1
                break
            except Exception as exc:   # one bad file must not stop the rest
                print(f"\n    FAILED: {exc}")
                _set_status(material_id, indexing.FAILED, indexing._explain(exc))
                failed += 1
                continue
            _set_status(material_id, indexing.READY, None)
            done += 1
            total_chunks += chunks
            print(f"\r    {chunks} chunks saved in {time.time() - started:.0f}s          ")
    finally:
        rag.set_job_progress(None)
    print(f"\nDone: {done} file(s) indexed ({total_chunks} chunks), {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
