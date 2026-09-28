import hashlib

# The four branches shown on the landing page and tracked (as mock data) per
# student. Add a real branch here once it exists — everything that reads
# progress goes through this one list.
BRANCHES = ["Algebra", "Geometry", "Statistics", "Calculus"]

# What a file can be tagged as when uploaded. "General" covers material that
# doesn't belong to one branch (and every file uploaded before tagging existed).
UPLOAD_BRANCHES = BRANCHES + ["General"]


def mock_progress(username: str, branch: str) -> int:
    """
    Deterministic placeholder progress percentage (0-100) for a given
    student + branch. This is NOT real lesson-completion tracking — there is
    no lessons/completions table yet, so this stands in for one. It's
    deterministic (same student+branch always gives the same number) so the
    UI doesn't look like it's flickering random values on every reload, and
    a student's landing page and their teacher's dashboard always agree.

    To replace with real tracking later: build a table of
    (student_id, branch, lesson_id, completed_at), compute the real
    percentage from it, and swap the body of this function — every caller
    (landing page progress bars, teacher dashboard) already goes through
    here, so nothing else needs to change.
    """
    digest = hashlib.md5(f"{username}:{branch}".encode()).hexdigest()
    return int(digest[:4], 16) % 101


def progress_for_user(username: str) -> list[dict]:
    return [{"branch": b, "percent": mock_progress(username, b)} for b in BRANCHES]
