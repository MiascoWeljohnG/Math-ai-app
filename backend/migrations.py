import hashlib
import re
from pathlib import Path

from sqlalchemy.orm import Session

from models import Material
from rag import store_uploaded_materials


def migrate_legacy_uploads(db: Session, legacy_dir: Path) -> list[Path]:
    if not legacy_dir.is_dir():
        return []

    migrated_paths = []
    try:
        legacy_files = sorted(path for path in legacy_dir.iterdir() if path.is_file())
        for legacy_file in legacy_files:
            legacy_name = legacy_file.name
            existing = db.query(Material).filter(Material.filename == legacy_name).first()
            display_name = (
                existing.display_name if existing and existing.display_name
                else re.sub(r"^[a-f0-9]{32}_", "", legacy_name, flags=re.IGNORECASE)
            )
            branch = existing.branch if existing and existing.branch else "General"
            storage_id = hashlib.sha256(legacy_name.encode("utf-8")).hexdigest()[:32]
            stored_path = store_uploaded_materials(
                [(display_name, legacy_file.read_bytes())],
                branch,
                storage_ids=[storage_id],
            )[0]

            material = existing or db.query(Material).filter(Material.filename == stored_path).first()
            if material is None:
                material = Material(
                    filename=stored_path,
                    display_name=display_name,
                    branch=branch,
                    uploaded_by="legacy",
                )
                db.add(material)
            else:
                material.filename = stored_path
                material.display_name = display_name
                material.branch = branch
            migrated_paths.append(legacy_file)

        db.commit()
    except Exception:
        db.rollback()
        raise
    return migrated_paths
