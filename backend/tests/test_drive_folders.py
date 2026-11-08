"""Drive sub-folders (Modules / Certificate of Enrollment / Archived) against a tiny in-memory fake of the Drive API."""
import itertools
import re

import pytest

import config
import drive_storage

ROOT = "root-folder"
FOLDER = drive_storage._FOLDER_MIME


class _Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self, num_retries=0):
        return self.fn()


class FakeDrive:
    """files: id -> {name, mime, parents}. Understands just the queries drive_storage sends."""

    def __init__(self):
        self.files = {ROOT: {"name": "Isipnayan uploads", "mime": FOLDER, "parents": []}}
        self.ids = itertools.count(1)

    def files_api(self):
        return self

    # the google client calls service.files().create(...)
    def create(self, body, fields=None, media_body=None, supportsAllDrives=None):
        def run():
            fid = f"f{next(self.ids)}"
            self.files[fid] = {"name": body["name"], "mime": body.get("mimeType", "application/pdf"), "parents": list(body["parents"])}
            return {"id": fid}
        return _Req(run)

    def get(self, fileId, fields=None, supportsAllDrives=None):
        def run():
            if fileId not in self.files:
                raise _NotFound()
            return {"parents": list(self.files[fileId]["parents"])}
        return _Req(run)

    def update(self, fileId, addParents="", removeParents="", fields=None, supportsAllDrives=None, body=None):
        def run():
            parents = self.files[fileId]["parents"]
            for p in filter(None, removeParents.split(",")):
                parents.remove(p)
            if addParents:
                parents.append(addParents)
            return {"id": fileId}
        return _Req(run)

    def list(self, q, fields=None, pageSize=None, pageToken=None, supportsAllDrives=None, includeItemsFromAllDrives=None):
        def run():
            parent = re.search(r"'([^']+)' in parents", q).group(1)
            name = re.search(r"name = '([^']+)'", q)
            only_folders = f"mimeType = '{FOLDER}'" in q
            no_folders = f"mimeType != '{FOLDER}'" in q
            out = []
            for fid, f in self.files.items():
                if parent not in f["parents"]:
                    continue
                if name and f["name"] != name.group(1):
                    continue
                if only_folders and f["mime"] != FOLDER:
                    continue
                if no_folders and f["mime"] == FOLDER:
                    continue
                out.append({"id": fid, "name": f["name"]})
            return {"files": out}
        return _Req(run)

    def named(self, name):
        return [fid for fid, f in self.files.items() if f["name"] == name]


def _NotFound():
    """What Google's client really raises for a missing file."""
    import httplib2
    from googleapiclient.errors import HttpError
    return HttpError(httplib2.Response({"status": "404"}), b"{}")


@pytest.fixture
def drive(monkeypatch):
    fake = FakeDrive()
    service = type("Service", (), {"files": lambda self: fake})()
    monkeypatch.setattr(config, "DRIVE_FOLDER_ID", ROOT)
    monkeypatch.setattr(drive_storage, "_service", lambda: service)
    monkeypatch.setattr(drive_storage, "_folder_ids", {})
    return fake


def _parent_name(fake, fid):
    return fake.files[fake.files[fid]["parents"][0]]["name"]


def test_modules_and_student_images_go_to_their_own_folders(drive):
    module = drive_storage.upload_bytes("abc_MODULE 1.pdf", b"x")
    cert = drive_storage.upload_bytes("cert_1.jpg", b"y", folder=drive_storage.STUDENT_IMAGES)
    assert _parent_name(drive, module) == "Modules"
    assert _parent_name(drive, cert) == "Certificate of Enrollment"
    assert drive.files[drive.files[module]["parents"][0]]["parents"] == [ROOT]   # the folders sit inside the main folder


def test_folders_are_created_once_and_reused(drive, monkeypatch):
    drive_storage.upload_bytes("a.pdf", b"x")
    drive_storage.upload_bytes("b.pdf", b"x")
    monkeypatch.setattr(drive_storage, "_folder_ids", {})       # as after a server restart: found by name, not duplicated
    drive_storage.upload_bytes("c.pdf", b"x")
    assert len(drive.named("Modules")) == 1


def test_archive_moves_the_file_and_does_not_trash_it(drive):
    module = drive_storage.upload_bytes("abc_MODULE 1.pdf", b"x")
    drive_storage.archive_file(module)
    assert _parent_name(drive, module) == "Archived"
    assert len(drive.files[module]["parents"]) == 1              # moved, not copied
    drive_storage.archive_file(module)                           # archiving twice is harmless
    assert _parent_name(drive, module) == "Archived"


def test_archiving_a_file_that_is_already_gone_is_fine(drive):
    drive_storage.archive_file("does-not-exist")                 # no exception


def test_organize_existing_sorts_loose_files_and_leaves_the_rest(drive):
    drive.files["m1"] = {"name": "h1_MODULE 1.pdf", "mime": "application/pdf", "parents": [ROOT]}
    drive.files["m2"] = {"name": "h2_Lesson 2.pdf", "mime": "application/pdf", "parents": [ROOT]}
    drive.files["c1"] = {"name": "cert_a09e.jpg", "mime": "image/jpeg", "parents": [ROOT]}
    already = drive_storage.upload_bytes("new.pdf", b"x")        # already inside Modules

    assert drive_storage.organize_existing(dry_run=True) == {"modules": 2, "student_images": 1}
    assert drive.files["m1"]["parents"] == [ROOT]                # a dry run moves nothing
    assert drive_storage.organize_existing() == {"modules": 2, "student_images": 1}
    assert _parent_name(drive, "m1") == _parent_name(drive, "m2") == "Modules"
    assert _parent_name(drive, "c1") == "Certificate of Enrollment"
    assert _parent_name(drive, already) == "Modules"
    assert drive_storage.organize_existing() == {"modules": 0, "student_images": 0}   # safe to run again
