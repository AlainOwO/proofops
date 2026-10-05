import os
import secrets
from urllib.parse import urlsplit

import pytest
from dotenv import dotenv_values
from proofops.auth import security_configuration
from proofops.config import APP_ROOT, Settings

from scripts import configure_local


def test_fresh_setup_creates_private_random_secrets_and_preserves_them(
    tmp_path, monkeypatch, capsys
):
    (tmp_path / ".env.example").write_text((APP_ROOT / ".env.example").read_text())
    monkeypatch.setattr(configure_local, "ROOT", tmp_path)
    configure_local.configure()
    path = tmp_path / ".env"
    original = path.read_bytes()
    values = dotenv_values(path)
    security_configuration(Settings(_env_file=None, secret_key=values["SECRET_KEY"]))
    assert len(values["POSTGRES_PASSWORD"]) >= 32
    assert urlsplit(values["DATABASE_URL"]).password == values["POSTGRES_PASSWORD"]
    assert values["SECRET_KEY"] != values["POSTGRES_PASSWORD"]
    assert not values["PROOFOPS_ADMIN_PASSWORD"] and not values["PROOFOPS_ADMIN_USERNAME"]
    assert values["AI_MODE"] == "off"
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    configure_local.configure()
    assert path.read_bytes() == original
    output = capsys.readouterr().out
    assert values["SECRET_KEY"] not in output and values["POSTGRES_PASSWORD"] not in output


def test_upgrade_preserves_existing_database_credentials_and_session_secret(tmp_path, monkeypatch):
    password, key = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    database_url = f"postgresql+psycopg://proofops:{password}@127.0.0.1:55432/proofops"
    (tmp_path / ".env").write_text(f"DATABASE_URL={database_url}\nSECRET_KEY={key}\nAI_MODE=off\n")
    monkeypatch.setattr(configure_local, "ROOT", tmp_path)
    configure_local.configure()
    values = dotenv_values(tmp_path / ".env")
    assert values["DATABASE_URL"] == database_url
    assert values["POSTGRES_PASSWORD"] == password
    assert values["SECRET_KEY"] == key


def test_setup_does_not_follow_an_environment_symlink(tmp_path, monkeypatch):
    target = tmp_path / "separate-environment"
    target.write_text("preserve this file")
    (tmp_path / ".env").symlink_to(target)
    monkeypatch.setattr(configure_local, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="regular file inside this repository"):
        configure_local.configure()
    assert target.read_text() == "preserve this file"
