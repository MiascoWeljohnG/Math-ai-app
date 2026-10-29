from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from pathlib import Path
import re
from datetime import date
from pydantic import BaseModel
from typing import Optional

from auth import require_school_admin, hash_password, check_password_strength
from database import get_db
from models import ACTIVE, AuditLog, User, UsageLog, Material, RegisteredStudent, School
from notifications import notify_admins
from classifier import AUTO, ingest_with_detection
from routes.materials_routes import material_summary
import config
import drive_storage

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/upload")
async def upload_documents(
    files: list[UploadFile] = File(...),
    branch: str = Form(AUTO),
    branches: str = Form(""),
    user=Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    # branch=Auto: the AI picks each file's branch and only asks when it isn't sure (classifier.py)
    return await ingest_with_detection(files, branch, branches, user.username, db)

@router.get("/users")
def list_users(user=Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.school_id == user.school_id).all()
    schools = {s.id: s.name for s in db.query(School)}
    return [
        {
            "school_id": u.school_id,
            "school": schools.get(u.school_id),
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "middle_name": u.middle_name,
            "email": u.email,
            "birthday": u.birthday,
            "role": u.role,
            "status": u.status,
            "created": str(u.created_at),
        }
        for u in users
    ]

@router.get("/files")
def list_files(user=Depends(require_admin), db: Session = Depends(get_db)):
    """Every uploaded file with who uploaded it and when (newest first)."""
    names = {u.username: u.person_name for u in db.query(User).all()}
    rows = db.query(Material).filter(Material.school_id == user.school_id).order_by(Material.uploaded_at.desc(), Material.id.desc()).all()
    return [{**material_summary(m), "uploaded_by_name": names.get(m.uploaded_by, "")} for m in rows]

@router.delete("/files/{filename:path}")
def delete_file(filename: str, user=Depends(require_admin), db: Session = Depends(get_db)):
    """Delete one uploaded file: its record, the original on disk, and the AI's chunks from it."""
    from rag import delete_material_chunks
    material = db.query(Material).filter(Material.filename == filename, Material.school_id == user.school_id).first()
    if material is None:
        raise HTTPException(status_code=404, detail="File not found")

    if material.drive_file_id:
        try:   # first, so a Drive failure leaves everything as it was and the delete can simply be retried
            drive_storage.delete_file(material.drive_file_id)
        except drive_storage.DriveStorageError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    delete_material_chunks(material.filename)
    vault_dir = Path(config.CHROMA_VAULT_DIR).expanduser().resolve()
    target = (vault_dir / material.filename).resolve()
    if vault_dir in target.parents and target.is_file():   # same path check as materials_routes: never delete outside the uploads folder
        target.unlink()

    name = material.display_name
    db.delete(material)
    notify_admins(db, "file_deleted", "File deleted", f'@{user.username} deleted "{name}" from the knowledge base.', exclude=user.username)
    db.commit()
    return {"message": f'Deleted "{name}".'}


@router.delete("/knowledge-base")
def clear_knowledge_base(user=Depends(require_admin), db: Session = Depends(get_db)):
    """Wipes the vector store, uploaded files, and their branch
    records together, so the materials list and the AI's searchable content
    can never disagree about what exists."""
    # Drive first: if any file can't be removed nothing else is touched, and running this again
    # is safe (a file that's already gone from Drive counts as removed).
    for drive_file_id in [row[0] for row in db.query(Material.drive_file_id).filter(Material.drive_file_id.isnot(None)).all()]:
        try:
            drive_storage.delete_file(drive_file_id)
        except drive_storage.DriveStorageError as exc:
            raise HTTPException(status_code=502, detail=f"Nothing was cleared: {exc}")

    import chromadb
    client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
    try:
        client.delete_collection(config.CHROMA_COLLECTION)
    except Exception:
        pass

    vault_collection = client.get_or_create_collection(name=config.CHROMA_VAULT_COLLECTION)
    uploaded_material_chunks = vault_collection.get(
        where={"type": "uploaded_material"},
        include=["metadatas"],
    )
    if uploaded_material_chunks["ids"]:
        vault_collection.delete(ids=uploaded_material_chunks["ids"])

    import shutil
    uploaded_material_dir = Path(config.CHROMA_VAULT_DIR).expanduser() / "Uploaded Materials"
    if uploaded_material_dir.is_dir():
        shutil.rmtree(uploaded_material_dir)

    db.query(Material).delete()
    notify_admins(db, "kb_cleared", "Knowledge base cleared", f"@{user.username} deleted every uploaded file.", exclude=user.username)
    db.commit()
    return {"message": "Knowledge base cleared. Re-upload your documents."}


class CreateTeacherRequest(BaseModel):
    username: str
    last_name: str
    first_name: str
    middle_name: str = ""   # optional
    email: str
    birthday: str = ""   # YYYY-MM-DD
    password: str
    school_id: Optional[int] = None   # which school the account is for; None = the main pool


def school_or_400(db: Session, school_id: Optional[int]) -> School:
    """Every account and every student number belongs to one of the two fixed schools."""
    if school_id is None:
        raise HTTPException(status_code=400, detail="Choose a school")
    school = db.query(School).filter(School.id == school_id).first()
    if school is None:
        raise HTTPException(status_code=400, detail="That school does not exist")
    return school


def new_account(req: CreateTeacherRequest, role: str, school_id: int, db: Session, actor: str = "system") -> User:
    """Validate and save one staff account (teacher or school admin). school_admin_routes calls this too, so a
    school admin makes teachers by exactly the same rules. Staff accounts are made by someone who is already
    trusted, so they start ACTIVE (only self-service student sign-ups go through approval)."""
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    check_password_strength(req.password)

    birthday = (req.birthday or "").strip()
    if not birthday:
        raise HTTPException(status_code=400, detail="Birthday is required")
    try:
        born = date.fromisoformat(birthday)
    except ValueError:
        raise HTTPException(status_code=400, detail="Birthday must be a valid date (YYYY-MM-DD)")
    if born > date.today():
        raise HTTPException(status_code=400, detail="Birthday cannot be in the future")

    last_name = " ".join((req.last_name or "").split())
    first_name = " ".join((req.first_name or "").split())
    if not last_name or not first_name:
        raise HTTPException(status_code=400, detail="Last name and first name are required")

    account = User(
        username=req.username,
        first_name=first_name,
        last_name=last_name,
        middle_name=" ".join((req.middle_name or "").split()),
        email=req.email,
        birthday=birthday,
        password_hash=hash_password(req.password),
        role=role,
        school_id=school_id,
        status=ACTIVE,
    )
    db.add(account)
    db.add(AuditLog(actor=actor, action=f"{role}.create", target=req.username, detail=f"school_id={school_id}"))
    db.commit()
    return account


@router.post("/create-teacher")
def create_teacher(
    req: CreateTeacherRequest,
    user=Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    # Teachers are never self-registered through the public /auth/register
    # form (that always creates role="user") - only an admin can grant
    # teacher access, so this is the one place a "teacher" role gets created
    # (school admins make teachers for their own school in school_admin_routes.py).
    school = school_or_400(db, req.school_id)
    new_account(req, "teacher", school.id, db, actor=user.username)
    return {"message": f"Teacher account '{req.username}' created for {school.name}."}


@router.post("/create-admin")
def create_admin(
    req: CreateTeacherRequest,
    user=Depends(require_school_admin),
    db: Session = Depends(get_db),
):
    """Admin creation is locked down three ways: only the super admin (a flag on the account, set at startup
    or by create_admin.py) can call this; it can only make a SCHOOL admin, for one of the two schools, so no
    API call ever produces another all-powerful account; and every creation is written to the audit log."""
    school = school_or_400(db, req.school_id)
    new_account(req, "school_admin", school.id, db, actor=user.username)
    return {"message": f"{school.name} admin account '{req.username}' created."}


@router.get("/audit-log")
def audit_log(limit: int = 200, user=Depends(require_school_admin), db: Session = Depends(get_db)):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 500))).all()
    return [{"at": r.created_at.isoformat() + "Z", "actor": r.actor, "action": r.action, "target": r.target, "detail": r.detail} for r in rows]


# ---- Registered student numbers (the sign-up list). Shared with school_admin_routes. ----
NUMBER_FORMAT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,39}")
MAX_NUMBERS_PER_REQUEST = 2000


class RegisteredNumbersRequest(BaseModel):
    numbers: str                      # pasted list: one per line, or separated by commas/spaces
    school_id: Optional[int] = None   # ignored for school admins (their own school is always used)


def add_registered(db: Session, raw: str, school_id: Optional[int]) -> dict:
    """Register the student numbers in `raw` for one school. Bad or duplicate numbers are skipped and
    reported back instead of failing the whole list."""
    numbers = list(dict.fromkeys(n for n in re.split(r"[\s,;]+", raw or "") if n))
    if not numbers:
        raise HTTPException(status_code=400, detail="Enter at least one student number")
    if len(numbers) > MAX_NUMBERS_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"Add at most {MAX_NUMBERS_PER_REQUEST} numbers at a time")
    taken = {n for (n,) in db.query(RegisteredStudent.student_number).filter(RegisteredStudent.student_number.in_(numbers))}
    has_account = {u for (u,) in db.query(User.username).filter(User.username.in_(numbers))}
    added, skipped = 0, []
    for number in numbers:
        if not NUMBER_FORMAT.fullmatch(number):
            skipped.append({"number": number, "reason": "not a valid student number"})
        elif number in taken:
            skipped.append({"number": number, "reason": "already registered"})
        elif number in has_account:
            skipped.append({"number": number, "reason": "already has an account"})
        else:
            db.add(RegisteredStudent(student_number=number, school_id=school_id))
            added += 1
    db.commit()
    return {"added": added, "skipped": skipped}


def registry_items(db: Session, rows) -> list[dict]:
    schools = {s.id: s.name for s in db.query(School)}
    signed_up = {u for (u,) in db.query(User.username).filter(User.role == "user")}
    return [
        {"id": r.id, "student_number": r.student_number, "school_id": r.school_id,
         "school": schools.get(r.school_id), "signed_up": r.student_number in signed_up}
        for r in rows
    ]


def remove_registered(db: Session, row: Optional[RegisteredStudent]) -> dict:
    if row is None:
        raise HTTPException(status_code=404, detail="Student number not found")
    if db.query(User).filter(User.username == row.student_number).first():
        raise HTTPException(status_code=400, detail="That student has already signed up")
    db.delete(row)
    db.commit()
    return {"message": f"{row.student_number} removed."}


@router.post("/registered-students")
def add_registered_students(req: RegisteredNumbersRequest, user=Depends(require_admin), db: Session = Depends(get_db)):
    school = school_or_400(db, req.school_id)
    return add_registered(db, req.numbers, school.id)


@router.get("/registered-students")
def list_registered_students(user=Depends(require_admin), db: Session = Depends(get_db)):
    return registry_items(db, db.query(RegisteredStudent).order_by(RegisteredStudent.id.desc()).all())


@router.delete("/registered-students/{row_id}")
def delete_registered_student(row_id: int, user=Depends(require_admin), db: Session = Depends(get_db)):
    return remove_registered(db, db.query(RegisteredStudent).filter(RegisteredStudent.id == row_id).first())
