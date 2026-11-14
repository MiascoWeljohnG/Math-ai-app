"""The teacher's bell (upload and lesson results, quiz violations) and the quiz lock: a student whose quiz was ended for
violations cannot retake it until a teacher approves their feedback."""
import json
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import indexing
from auth import get_current_user
from database import get_db
from models import Lesson, LessonQuiz, Material, Notification, QuizAttempt, QuizRetakeRequest, Subject, User
from routes import notification_routes, retake_routes, subjects_routes as sr

QUESTIONS = [
    {"type": "tf", "question": "1 + 1 = 2", "answer": True, "explanation": "Yes."},
    {"type": "tf", "question": "2 + 2 = 5", "answer": False, "explanation": "No."},
]
FEEDBACK = "My internet dropped and the tab reloaded, I did not leave on purpose."


@pytest.fixture
def world(db):
    def user(name, role, school=1):
        row = User(username=name, password_hash="x", role=role, school_id=school, status="active", first_name=name.title())
        db.add(row)
        return row

    student, other_student = user("stu", "user"), user("stu2", "user")
    teacher, teacher2, outsider = user("teach", "teacher"), user("teach2", "teacher"), user("far", "teacher", school=2)
    admin = user("boss", "school_admin")
    shared = Subject(name="Algebra", school_id=1)
    personal = Subject(name="My notes", owner_user_id=None)   # owner set below, once the student has an id
    db.add_all([shared, personal])
    db.commit()
    personal.owner_user_id = student.id
    lesson = Lesson(subject_id=shared.id, title="Linear equations", content="x", created_by="teach", status="published")
    own_lesson = Lesson(subject_id=personal.id, title="My lesson", content="x", created_by="stu", status="published")
    db.add_all([lesson, own_lesson])
    db.commit()
    db.add_all([LessonQuiz(lesson_id=lesson.id, questions=json.dumps(QUESTIONS), difficulty=3),
                LessonQuiz(lesson_id=own_lesson.id, questions=json.dumps(QUESTIONS), difficulty=3)])
    db.commit()

    app, current = FastAPI(), {"user": student}
    for router in (sr.router, retake_routes.router, notification_routes.router):
        app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    client = TestClient(app)
    return types.SimpleNamespace(
        db=db, client=client, current=current, student=student, other_student=other_student, teacher=teacher,
        teacher2=teacher2, outsider=outsider, admin=admin, lesson=lesson, own_lesson=own_lesson,
        quiz=f"/subjects/{shared.id}/lessons/{lesson.id}/quiz",
        own_quiz=f"/subjects/{personal.id}/lessons/{own_lesson.id}/quiz",
        shared=shared,
    )


def as_user(w, who):
    w.current["user"] = who


def kinds_for(w, username):
    return [n.kind for n in w.db.query(Notification).filter(Notification.admin_username == username).order_by(Notification.id)]


def finish_quiz(w, violations=0, base=None):
    return w.client.post((base or w.quiz) + "/submit", json={"answers": {"0": True, "1": False}, "seconds": 30, "violations": violations})


# ---------------------------------------------------------------- violations lock the quiz
def test_ending_a_quiz_for_violations_locks_it_and_tells_the_teachers_of_that_school(world):
    result = finish_quiz(world, violations=3).json()
    assert result["lock"]["status"] == "locked" and result["lock"]["can_request"] is True
    assert result["recorded"] is True                           # the attempt still counts, as before
    assert kinds_for(world, "teach") == ["quiz_violation"]
    assert kinds_for(world, "teach2") == ["quiz_violation"]     # every teacher of the school hears about it
    assert kinds_for(world, "far") == [] and kinds_for(world, "boss") == []   # not another school, not the admin
    assert "Stu" in world.db.query(Notification).filter(Notification.admin_username == "teach").one().message


def test_locked_student_gets_no_questions_and_cannot_submit(world):
    finish_quiz(world, violations=3)
    page = world.client.get(world.quiz).json()
    assert page["quiz"] is None and page["lock"]["status"] == "locked"
    assert world.client.post(world.quiz + "/generate").json()["lock"]["status"] == "locked"
    assert finish_quiz(world).status_code == 403
    assert world.db.query(QuizAttempt).count() == 1             # the blocked submit was not recorded


def test_the_lock_is_per_student_and_per_lesson(world):
    finish_quiz(world, violations=3)
    as_user(world, world.other_student)
    assert world.client.get(world.quiz).json()["quiz"] is not None


def test_fewer_than_three_violations_do_not_lock(world):
    assert finish_quiz(world, violations=2).json()["lock"] is None
    assert world.db.query(QuizRetakeRequest).count() == 0 and kinds_for(world, "teach") == []
    assert world.client.get(world.quiz).json()["quiz"] is not None


def test_a_teacher_previewing_a_quiz_is_never_locked(world):
    as_user(world, world.teacher)
    result = finish_quiz(world, violations=3).json()
    assert result["recorded"] is False and result["lock"] is None
    assert world.db.query(QuizRetakeRequest).count() == 0


def test_a_students_own_subject_has_no_teacher_so_it_never_locks(world):
    assert finish_quiz(world, violations=3, base=world.own_quiz).json()["lock"] is None
    assert world.client.get(world.own_quiz).json()["quiz"] is not None


# ---------------------------------------------------------------- feedback, approval, rejection
def test_student_asks_teacher_decides_student_retakes_once(world):
    finish_quiz(world, violations=3)
    ask = world.client.post(world.quiz + "/retake-request", json={"feedback": FEEDBACK})
    assert ask.json()["lock"]["status"] == "pending"
    assert "retake_request" in kinds_for(world, "teach")
    assert world.client.get(world.quiz).json()["lock"]["status"] == "pending"      # still locked while waiting

    as_user(world, world.teacher)
    listing = world.client.get("/retake-requests").json()
    assert listing["pending"] == 1 and listing["items"][0]["feedback"] == FEEDBACK
    request_id = listing["items"][0]["id"]
    assert world.client.post(f"/retake-requests/{request_id}/decision", json={"approve": True}).status_code == 200

    as_user(world, world.student)
    page = world.client.get(world.quiz).json()
    assert page["lock"] is None and page["quiz"] is not None and page["retake_approved"] is True
    assert finish_quiz(world).json()["lock"] is None                               # the retake itself
    assert world.db.query(QuizRetakeRequest).one().status == "used"                # spent
    assert world.client.get(world.quiz).json()["retake_approved"] is False
    assert finish_quiz(world).status_code == 200                                    # a normal quiz again


def test_rejected_student_stays_locked_sees_the_note_and_may_ask_again(world):
    finish_quiz(world, violations=3)
    world.client.post(world.quiz + "/retake-request", json={"feedback": FEEDBACK})
    as_user(world, world.teacher)
    request_id = world.client.get("/retake-requests").json()["items"][0]["id"]
    world.client.post(f"/retake-requests/{request_id}/decision", json={"approve": False, "note": "Please review the lesson first."})

    as_user(world, world.student)
    lock = world.client.get(world.quiz).json()["lock"]
    assert lock["status"] == "rejected" and lock["teacher_note"] == "Please review the lesson first." and lock["can_request"]
    assert finish_quiz(world).status_code == 403
    again = world.client.post(world.quiz + "/retake-request", json={"feedback": "I reviewed the lesson, sorry about before."})
    assert again.json()["lock"]["status"] == "pending" and again.json()["lock"]["teacher_note"] == ""


def test_violating_again_on_the_retake_locks_again(world):
    finish_quiz(world, violations=3)
    world.client.post(world.quiz + "/retake-request", json={"feedback": FEEDBACK})
    world.db.query(QuizRetakeRequest).one().status = "approved"
    world.db.commit()
    assert finish_quiz(world, violations=3).json()["lock"]["status"] == "locked"
    assert sorted(r.status for r in world.db.query(QuizRetakeRequest)) == ["locked", "used"]


def test_feedback_rules(world):
    assert world.client.post(world.quiz + "/retake-request", json={"feedback": FEEDBACK}).status_code == 409   # not locked
    finish_quiz(world, violations=3)
    assert world.client.post(world.quiz + "/retake-request", json={"feedback": "sorry"}).status_code == 400    # too short
    assert world.client.post(world.quiz + "/retake-request", json={"feedback": FEEDBACK}).status_code == 200
    assert world.client.post(world.quiz + "/retake-request", json={"feedback": FEEDBACK}).status_code == 409   # already sent


def test_only_staff_of_the_same_school_decide(world):
    finish_quiz(world, violations=3)
    world.client.post(world.quiz + "/retake-request", json={"feedback": FEEDBACK})
    request_id = world.db.query(QuizRetakeRequest).one().id
    assert world.client.get("/retake-requests").status_code == 403                                  # a student
    as_user(world, world.outsider)
    assert world.client.get("/retake-requests").json()["items"] == []                              # another school's teacher
    assert world.client.post(f"/retake-requests/{request_id}/decision", json={"approve": True}).status_code == 404
    as_user(world, world.admin)                                                                     # the school admin can
    assert world.client.post(f"/retake-requests/{request_id}/decision", json={"approve": True}).status_code == 200
    assert world.client.post(f"/retake-requests/{request_id}/decision", json={"approve": False}).status_code == 409   # only once


def test_deleting_a_lesson_removes_its_locks(world):
    finish_quiz(world, violations=3)
    sr.delete_lesson_cascade(world.db, world.lesson)
    world.db.commit()
    assert world.db.query(QuizRetakeRequest).count() == 0


# ---------------------------------------------------------------- the teacher's bell
def test_teacher_reads_only_their_own_bell(world):
    finish_quiz(world, violations=3)
    as_user(world, world.teacher)
    body = world.client.get("/notifications").json()
    assert body["unread"] == 1 and body["items"][0]["kind"] == "quiz_violation"
    world.client.post("/notifications/read-all")
    assert world.client.get("/notifications").json()["unread"] == 0
    as_user(world, world.outsider)
    assert world.client.get("/notifications").json()["items"] == []
    as_user(world, world.student)
    assert world.client.get("/notifications").status_code == 403


def add_material(db, uploader="teach", name="a.pdf"):
    row = Material(filename=f"Uploaded Materials/Algebra/id_{name}", display_name=name, branch="Algebra",
                   uploaded_by=uploader, index_status="indexing")
    db.add(row)
    db.commit()
    return row


def test_upload_result_reaches_the_teacher_who_uploaded_it(world, monkeypatch):
    monkeypatch.setattr(indexing, "SessionLocal", sessionmaker(bind=world.db.get_bind()))
    ok, bad = add_material(world.db), add_material(world.db, name="b.pdf")
    assert indexing._finish(ok.id, indexing.READY, None)
    assert indexing._finish(bad.id, indexing.FAILED, "No readable text found in a.pdf.")
    rows = world.db.query(Notification).filter(Notification.admin_username == "teach").order_by(Notification.id).all()
    assert [r.kind for r in rows] == ["upload_ok", "upload_failed"]
    assert "b.pdf" in rows[1].message and "No readable text" in rows[1].message and "Retry" in rows[1].message
    assert kinds_for(world, "boss") == [] and kinds_for(world, "teach2") == []


def test_an_upload_by_someone_who_is_not_a_teacher_adds_nothing(world, monkeypatch):
    monkeypatch.setattr(indexing, "SessionLocal", sessionmaker(bind=world.db.get_bind()))
    row = add_material(world.db, uploader="boss")
    indexing._finish(row.id, indexing.READY, None)
    assert world.db.query(Notification).count() == 0


def compose(world, title="Factoring"):
    return world.client.post(f"/subjects/{world.shared.id}/lessons/compose", data={"title": title, "description": "", "save": "true"})


def test_a_generated_lesson_and_a_failed_one_both_reach_the_teacher(world, monkeypatch):
    as_user(world, world.teacher)

    async def writes(*args, **kwargs):
        return "A fine lesson."
    monkeypatch.setattr(sr, "generate_text", writes)
    assert compose(world).status_code == 200

    async def breaks(*args, **kwargs):
        raise RuntimeError("model is down")
    monkeypatch.setattr(sr, "generate_text", breaks)
    assert compose(world, "Graphs").status_code == 502

    rows = world.db.query(Notification).filter(Notification.admin_username == "teach").order_by(Notification.id).all()
    assert [r.kind for r in rows] == ["lesson_ready", "lesson_failed"]
    assert "Factoring" in rows[0].message and "Drafts" in rows[0].message
    assert "Graphs" in rows[1].message and "model is down" in rows[1].message
    assert world.db.query(Lesson).filter(Lesson.title == "Graphs").count() == 0       # nothing half-saved
