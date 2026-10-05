import hashlib
import os
import secrets
from types import SimpleNamespace

import pytest
from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url

from scripts import rotate_local_database_password as rotation


def private_environment(tmp_path, **overrides):
    password = secrets.token_urlsafe(32)
    url = URL.create(
        "postgresql+psycopg",
        username="proofops",
        password=password,
        host="127.0.0.1",
        port=55432,
        database="proofops",
    )
    values = {
        "DATABASE_URL": url.render_as_string(hide_password=False),
        "POSTGRES_PASSWORD": password,
        "PROOFOPS_MODE": "local",
        "SECRET_KEY": secrets.token_urlsafe(48),
        "AI_MODE": "off",
        **overrides,
    }
    target = tmp_path / ".env"
    target.write_text(
        "# Preserve operator settings.\n" + "".join(f"{k}={v}\n" for k, v in values.items())
    )
    target.chmod(0o600)
    return target, values


class FakeDatabase:
    """Model transactions and password authentication independently of rotation code."""

    def __init__(self, password, target):
        self.password = password
        self.target = target
        self.changes = 0
        self.statements = []
        self.fail_commit = False

    def connect(self, url):
        if url.password != self.password:
            raise RuntimeError("Simulated authentication failure: " + url.password)
        assert self.target.with_name(".env.database-rotation.pending").is_file()
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, database):
        self.database = database
        self.next_password = None
        self.pgconn = SimpleNamespace(encrypt_password=self.encrypt_password)

    def encrypt_password(self, password, username, algorithm):
        assert username == b"proofops" and algorithm == b"scram-sha-256"
        self.next_password = password.decode()
        return ("SCRAM-SHA-256$" + hashlib.sha256(password).hexdigest()).encode()

    def execute(self, statement):
        if statement == "SELECT 1":
            return SimpleNamespace(fetchone=lambda: (1,))
        self.database.statements.append(statement.as_string())
        assert self.database.statements[-1].startswith('ALTER ROLE "proofops" PASSWORD ')

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind is None and self.next_password:
            if self.database.fail_commit:
                raise RuntimeError("Simulated commit failure: " + self.next_password)
            self.database.password = self.next_password
            self.database.changes += 1


def test_rotation_synchronizes_credentials_preserves_settings_and_uses_private_recovery(
    tmp_path, monkeypatch, capsys
):
    target, before = private_environment(tmp_path)
    database = FakeDatabase(before["POSTGRES_PASSWORD"], target)
    monkeypatch.setattr(rotation, "_connect", database.connect)
    rotation.rotate(target)
    after = dotenv_values(target)
    assert bool(after["POSTGRES_PASSWORD"] != before["POSTGRES_PASSWORD"])
    assert bool(database.password == after["POSTGRES_PASSWORD"])
    assert bool(make_url(after["DATABASE_URL"]).password == after["POSTGRES_PASSWORD"])
    assert len(after["POSTGRES_PASSWORD"]) >= 32
    assert bool(after["SECRET_KEY"] == before["SECRET_KEY"])
    assert after["AI_MODE"] == "off" and after["PROOFOPS_MODE"] == "local"
    assert target.read_text().startswith("# Preserve operator settings.\n")
    assert not target.with_name(".env.database-rotation.pending").exists()
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600
    diagnostics = capsys.readouterr().out + " ".join(database.statements)
    for value in (before["POSTGRES_PASSWORD"], after["POSTGRES_PASSWORD"], before["SECRET_KEY"]):
        assert bool(value in diagnostics) is False


@pytest.mark.parametrize(
    "kind", ["remote", "hosted", "mismatch", "query", "duplicate", "malformed"]
)
def test_rotation_rejects_ambiguous_or_nonlocal_configuration_before_connecting(
    tmp_path, monkeypatch, kind
):
    target, values = private_environment(tmp_path)
    url = make_url(values["DATABASE_URL"])
    if kind == "remote":
        values["DATABASE_URL"] = url.set(host="database.example").render_as_string(
            hide_password=False
        )
    elif kind == "hosted":
        values["PROOFOPS_MODE"] = "hosted"
    elif kind == "mismatch":
        values["POSTGRES_PASSWORD"] = secrets.token_urlsafe(32)
    elif kind == "query":
        values["DATABASE_URL"] += "?host=database.example"
    elif kind == "malformed":
        values["DATABASE_URL"] = secrets.token_urlsafe(32)
    content = "".join(f"{k}={v}\n" for k, v in values.items())
    if kind == "duplicate":
        content += "DATABASE_URL=" + values["DATABASE_URL"] + "\n"
    target.write_text(content)
    monkeypatch.setattr(
        rotation, "_connect", lambda _: pytest.fail("Must reject before connecting")
    )
    with pytest.raises(rotation.RotationError, match="Rotation requires local mode") as error:
        rotation.rotate(target)
    assert bool(values["POSTGRES_PASSWORD"] in str(error.value)) is False
    assert bool(target.read_text() == content)
    assert not target.with_name(".env.database-rotation.pending").exists()


@pytest.mark.parametrize("kind", ["symlink", "public", "pending_symlink"])
def test_rotation_does_not_follow_symlinks_or_use_public_credentials(tmp_path, monkeypatch, kind):
    target, values = private_environment(tmp_path)
    original = target.read_bytes()
    if kind == "symlink":
        destination = tmp_path / "other"
        target.rename(destination)
        target.symlink_to(destination)
    elif kind == "public":
        target.chmod(0o644)
    else:
        target.with_name(".env.database-rotation.pending").symlink_to(target)
    monkeypatch.setattr(
        rotation, "_connect", lambda _: pytest.fail("Must reject before connecting")
    )
    with pytest.raises(rotation.RotationError) as error:
        rotation.rotate(target, resume=kind == "pending_symlink")
    assert bool(target.read_bytes() == original)
    assert bool(values["POSTGRES_PASSWORD"] in str(error.value)) is False


def test_failed_commit_leaves_private_recovery_and_resume_completes(tmp_path, monkeypatch, capsys):
    target, before = private_environment(tmp_path)
    original = target.read_bytes()
    database = FakeDatabase(before["POSTGRES_PASSWORD"], target)
    database.fail_commit = True
    monkeypatch.setattr(rotation, "_connect", database.connect)
    with pytest.raises(rotation.RotationError, match="rerun with --resume") as error:
        rotation.rotate(target)
    pending = target.with_name(".env.database-rotation.pending")
    prepared = dotenv_values(pending)
    assert bool(target.read_bytes() == original)
    if os.name == "posix":
        assert pending.stat().st_mode & 0o777 == 0o600
    assert database.changes == 0
    with pytest.raises(rotation.RotationError, match="pending rotation exists"):
        rotation.rotate(target)
    database.fail_commit = False
    rotation.rotate(target, resume=True)
    assert database.changes == 1 and not pending.exists()
    assert bool(dotenv_values(target)["POSTGRES_PASSWORD"] == prepared["POSTGRES_PASSWORD"])
    output = capsys.readouterr().out + str(error.value)
    assert bool(prepared["POSTGRES_PASSWORD"] in output) is False


def test_failed_replace_recovers_with_new_credential_without_rotating_twice(
    tmp_path, monkeypatch, capsys
):
    target, before = private_environment(tmp_path)
    original = target.read_bytes()
    database = FakeDatabase(before["POSTGRES_PASSWORD"], target)
    monkeypatch.setattr(rotation, "_connect", database.connect)
    replace = rotation.os.replace

    def fail_replace(*args):
        raise PermissionError("Synthetic file failure")

    monkeypatch.setattr(rotation.os, "replace", fail_replace)
    with pytest.raises(rotation.RotationError, match="configuration recovery"):
        rotation.rotate(target)
    assert database.changes == 1 and bool(target.read_bytes() == original)
    monkeypatch.setattr(rotation.os, "replace", replace)
    rotation.rotate(target, resume=True)
    assert database.changes == 1
    assert bool(dotenv_values(target)["POSTGRES_PASSWORD"] == database.password)
    assert bool(database.password in capsys.readouterr().out) is False


def test_concurrent_operator_edits_are_preserved_for_private_reconciliation(tmp_path, monkeypatch):
    target, before = private_environment(tmp_path)
    database = FakeDatabase(before["POSTGRES_PASSWORD"], target)
    monkeypatch.setattr(rotation, "_connect", database.connect)
    verify = rotation._verify

    def edit_then_verify(url):
        target.write_text(target.read_text() + "AWS_REGION=us-east-1\n")
        verify(url)

    monkeypatch.setattr(rotation, "_verify", edit_then_verify)
    with pytest.raises(rotation.RotationError, match="configuration recovery"):
        rotation.rotate(target)
    assert "AWS_REGION=us-east-1" in target.read_text()
    assert target.with_name(".env.database-rotation.pending").exists()
    with pytest.raises(rotation.RotationError, match="reconcile it privately"):
        rotation.rotate(target, resume=True)
    assert database.changes == 1


def test_no_database_change_when_recovery_file_cannot_be_made_durable(tmp_path, monkeypatch):
    target, _ = private_environment(tmp_path)
    original = target.read_bytes()

    def fail_sync(_):
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(rotation.os, "fsync", fail_sync)
    monkeypatch.setattr(
        rotation, "_connect", lambda _: pytest.fail("Must prepare before connecting")
    )
    with pytest.raises(rotation.RotationError, match="no change made"):
        rotation.rotate(target)
    assert bool(target.read_bytes() == original)
    assert not target.with_name(".env.database-rotation.pending").exists()
