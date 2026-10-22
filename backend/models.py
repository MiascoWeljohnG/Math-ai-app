from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, UniqueConstraint, Boolean
from datetime import date, datetime
from database import Base

class School(Base):
    """One school (A, B ...). Accounts, subjects, files and reminders belong to a school through their
    `school_id`; school_id NULL is the main pool every account made before schools existed lives in."""
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RegisteredStudent(Base):
    """A student number the school has registered. Once any exist, only these numbers can sign up, and
    the student joins the school the number is listed under."""
    __tablename__ = "registered_students"

    id = Column(Integer, primary_key=True, index=True)
    student_number = Column(String, nullable=False, unique=True, index=True)
    school_id = Column(Integer, nullable=True, index=True)   # NULL = the main pool
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    middle_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    birthday = Column(String, nullable=True)
    # --- profile fields (added for the Edit Profile page) ---
    full_name = Column(String, nullable=True)
    student_id = Column(String, nullable=True)
    contact_number = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    address = Column(String, nullable=True)
    grade_section = Column(String, nullable=True)
    strand = Column(String, nullable=True)
    school_year = Column(String, nullable=True)
    avatar = Column(Text, nullable=True)  # small data-URL image
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")   # user | teacher | school_admin | admin (main admin)
    school_id = Column(Integer, nullable=True, index=True)   # NULL = the main pool
    created_at = Column(Date, default=date.today)

class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    date = Column(Date, default=date.today)
    count = Column(Integer, default=0)

class Conversation(Base):
    """One chat thread. A user can have many — this is what the 'New Chat'
    tabs in the sidebar switch between."""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    title = Column(String, nullable=False, default="New chat")
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatMessage(Base):
    """A single message in a conversation. Persisting these is what makes
    chat history survive logout/refresh instead of living only in browser
    memory."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True, nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    image_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)   

class Material(Base):
    """One uploaded course file, tagged with the math branch it belongs to.
    `filename` is the name on disk (with the hash prefix), which is what the
    materials routes and the vector store's `source` metadata both use."""
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=False)
    branch = Column(String, nullable=False, default="General")
    uploaded_by = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    school_id = Column(Integer, nullable=True, index=True)   # the uploader's school
    drive_file_id = Column(String, nullable=True)   # Google Drive file id of the original; None = a file on local disk


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    owner_user_id = Column(Integer, nullable=True, index=True)
    school_id = Column(Integer, nullable=True, index=True)   # which school's shared subject this is (personal subjects ignore it)
    created_at = Column(DateTime, default=datetime.utcnow)


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), index=True, nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    order_index = Column(Integer, default=0)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class LessonCompletion(Base):
    """A student marked a lesson as complete. This is what the progress bars count."""
    __tablename__ = "lesson_completions"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), index=True, nullable=False)
    completed_at = Column(DateTime, default=datetime.utcnow)


class LessonQuiz(Base):
    """One quiz per lesson. `questions` is JSON: [{type: mcq|tf|id|num, question, choices (mcq only), answer, explanation}]."""
    __tablename__ = "lesson_quizzes"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), unique=True, index=True, nullable=False)
    questions = Column(Text, nullable=False)
    difficulty = Column(Integer, nullable=True)   # 1-5, set by the AI; decides the time limit
    created_at = Column(DateTime, default=datetime.utcnow)


class SubjectDeletionRequest(Base):
    """A teacher/admin asked to delete a shared subject. It only disappears once EVERY admin approves.
    status: pending -> approved (subject deleted) | rejected (kept). subject_name is copied so the
    history still reads correctly after the subject is gone."""
    __tablename__ = "subject_deletion_requests"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, index=True, nullable=False)
    subject_name = Column(String, nullable=False)
    requested_by = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class SubjectDeletionVote(Base):
    """One admin's answer to a deletion request (approve=True/False). One row per admin per request."""
    __tablename__ = "subject_deletion_votes"
    __table_args__ = (UniqueConstraint("request_id", "admin_username"),)

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("subject_deletion_requests.id"), index=True, nullable=False)
    admin_username = Column(String, nullable=False)
    approve = Column(Boolean, nullable=False)
    decided_at = Column(DateTime, default=datetime.utcnow)


class Notification(Base):
    """One entry in an admin's bell. notify_admins() (notifications.py) writes them; routes/notification_routes.py reads them."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    admin_username = Column(String, index=True, nullable=False)
    kind = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False, default="")
    read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PracticeSet(Base):
    """The adaptive practice set a student was given for a lesson: easier after a weak quiz, harder after a
    strong one. `questions` has the same shape as LessonQuiz.questions. `attempt_id` is the quiz attempt it was
    written for, so a newer attempt means a new set. Practice is never graded into the leaderboard."""
    __tablename__ = "practice_sets"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), index=True, nullable=False)
    kind = Column(String, nullable=False)          # easier | harder
    questions = Column(Text, nullable=False)
    attempt_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class QuizAttempt(Base):
    """Every graded quiz attempt by a student. Feeds the leaderboard, the roadmap and the failed-quiz breakdown.
    `missed` is JSON: the question ids answered wrong. `breakdown` caches the AI's step-by-step explanation."""
    __tablename__ = "quiz_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), index=True, nullable=False)
    score = Column(Integer, nullable=False)
    total = Column(Integer, nullable=False)
    seconds = Column(Integer, nullable=True)      # time the student took, as reported by their browser
    passed = Column(Boolean, nullable=False, default=False)
    missed = Column(Text, nullable=False, default="[]")
    breakdown = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Reminder(Base):
    """A note from a teacher/admin. student_username None = shown to every student."""
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(String, nullable=False)
    created_by = Column(String, nullable=False)
    student_username = Column(String, index=True, nullable=True)
    due_date = Column(Date, nullable=True)
    school_id = Column(Integer, nullable=True, index=True)   # the author's school: only its students see "everyone" reminders
    created_at = Column(DateTime, default=datetime.utcnow)
