import os
import re
import secrets
import stat
import subprocess

import pytest

from scripts import configure_hosted


@pytest.fixture
def offline_bcrypt(monkeypatch):
    hashes = []

    def hash_password(password):
        hashed = "$2b$14$" + "".join(
            secrets.choice("./ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
            for _ in range(53)
        )
        hashes.append((password, hashed))
        return hashed

    monkeypatch.setattr(configure_hosted, "bcrypt_hash", hash_password)
    return hashes


def test_hosted_setup_generates_separate_private_secrets_and_preserves_them(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(configure_hosted, "ROOT", tmp_path)
    configure_hosted.configure("demo.example.com", "operator@example.com")
    target = tmp_path / ".env.hosted"
    content = target.read_text()
    values = dict(line.split("=", 1) for line in content.splitlines() if not line.startswith("#"))
    passwords = [values[name] for name in configure_hosted.SECRET_NAMES]
    assert len(set(passwords)) == len(passwords)
    assert all(len(password) >= 32 and len(set(password)) >= 16 for password in passwords)
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    configure_hosted.configure("demo.example.com", "operator@example.com")
    assert bool(target.read_text() == content)
    output = capsys.readouterr()
    assert all(not bool(password in output.out or password in output.err) for password in passwords)


@pytest.mark.parametrize(
    "domain,email",
    [
        ("https://demo.example.com", "operator@example.com"),
        ("demo.example.com:443", "operator@example.com"),
        ("demo.example.com\n}", "operator@example.com"),
        ("demo.example.com", "operator@example.com\n}"),
    ],
)
def test_hosted_setup_rejects_config_injection(tmp_path, monkeypatch, domain, email):
    monkeypatch.setattr(configure_hosted, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        configure_hosted.configure(domain, email)
    assert not (tmp_path / ".env.hosted").exists()


def test_hosted_setup_rejects_symlinked_or_ambiguous_private_files(tmp_path, monkeypatch):
    monkeypatch.setattr(configure_hosted, "ROOT", tmp_path)
    target = tmp_path / ".env.hosted"
    real = tmp_path / "private"
    real.write_text("retained")
    target.symlink_to(real)
    with pytest.raises(ValueError):
        configure_hosted.configure("demo.example.com", "operator@example.com")
    assert real.read_text() == "retained"
    target.unlink()
    target.write_text("SECRET_KEY=\nSECRET_KEY=\n")
    with pytest.raises(ValueError, match="ambiguous"):
        configure_hosted.configure("demo.example.com", "operator@example.com")


def test_full_setup_preserves_public_credentials_and_generates_private_independent_secrets(
    tmp_path, monkeypatch, capsys, offline_bcrypt
):
    monkeypatch.setattr(configure_hosted, "ROOT", tmp_path)
    configure_hosted.configure("demo.example.com", "operator@example.com")
    public = tmp_path / ".env.hosted"
    original = public.read_bytes()
    configure_hosted.configure_full("demo.example.com", "full.example.com", "operator@example.com")
    full = tmp_path / ".env.hosted-full"
    full_original = full.read_bytes()
    assert bool(public.read_bytes() == original)
    values = configure_hosted.read_private(full)
    assert values["FULL_DOMAIN"] == "full.example.com"
    passwords = list(offline_bcrypt[0]) + [
        values[name] for name in configure_hosted.FULL_SECRET_NAMES
    ]
    public_values = configure_hosted.read_private(public)
    deployment_secrets = [public_values[name] for name in configure_hosted.SECRET_NAMES] + [
        values[name] for name in configure_hosted.FULL_SECRET_NAMES
    ]
    assert len(set(deployment_secrets)) == len(deployment_secrets)
    assert all(len(value) >= 32 and len(set(value)) >= 16 for value in deployment_secrets)
    assert len(values["FULL_BASIC_AUTH_PASSWORD"]) <= 72
    assert re.fullmatch(configure_hosted.BCRYPT_PATTERN, values["FULL_BASIC_AUTH_HASH"])
    assert bool("FULL_BASIC_AUTH_HASH='" + values["FULL_BASIC_AUTH_HASH"] + "'" in full.read_text())
    assert stat.S_IMODE(full.stat().st_mode) == stat.S_IMODE(public.stat().st_mode) == 0o600
    configure_hosted.configure_full("demo.example.com", "full.example.com", "operator@example.com")
    assert bool(full.read_bytes() == full_original and public.read_bytes() == original)
    assert len(offline_bcrypt) == 1, "Existing gateway passwords and hashes must never be rotated"
    output = capsys.readouterr()
    assert all(
        not bool(secret in output.out or secret in output.err)
        for secret in passwords + deployment_secrets
    )


@pytest.mark.parametrize(
    "public_domain,full_domain,email",
    [
        ("demo.example.com", "demo.example.com", "operator@example.com"),
        ("https://demo.example.com", "full.example.com", "operator@example.com"),
        ("demo.example.com", "https://full.example.com", "operator@example.com"),
        ("demo.example.com", "full.example.com:443", "operator@example.com"),
        ("demo.example.com", "full.example.com\n}", "operator@example.com"),
        ("demo.example.com", "full.example.com", "operator@example.com\n}"),
    ],
)
def test_full_setup_rejects_invalid_addresses_before_writing(
    tmp_path, monkeypatch, public_domain, full_domain, email, offline_bcrypt
):
    monkeypatch.setattr(configure_hosted, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        configure_hosted.configure_full(public_domain, full_domain, email)
    assert list(tmp_path.iterdir()) == [] and offline_bcrypt == []


def test_full_setup_rejects_symlinked_full_configuration_without_changing_public(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(configure_hosted, "ROOT", tmp_path)
    configure_hosted.configure("demo.example.com", "operator@example.com")
    public = tmp_path / ".env.hosted"
    original = public.read_bytes()
    (tmp_path / ".env.hosted-full").symlink_to(public)
    with pytest.raises(ValueError, match="regular private file"):
        configure_hosted.configure_full(
            "demo.example.com", "full.example.com", "operator@example.com"
        )
    assert bool(public.read_bytes() == original)


@pytest.mark.parametrize(
    "field", ["FULL_RUNTIME_PASSWORD", "FULL_BASIC_AUTH_USER", "FULL_BASIC_AUTH_HASH", "SECRET_KEY"]
)
def test_full_setup_refuses_invalid_existing_credentials_without_overwriting(
    tmp_path, monkeypatch, offline_bcrypt, field
):
    monkeypatch.setattr(configure_hosted, "ROOT", tmp_path)
    configure_hosted.configure_full("demo.example.com", "full.example.com", "operator@example.com")
    public, full = tmp_path / ".env.hosted", tmp_path / ".env.hosted-full"
    values = configure_hosted.read_private(full)
    if field == "FULL_RUNTIME_PASSWORD":
        values[field] = configure_hosted.read_private(public)["PROOFOPS_RUNTIME_PASSWORD"]
    else:
        values[field] = "invalid value {}"
    configure_hosted.write_private(full, values)
    originals = [target.read_bytes() for target in (public, full)]
    with pytest.raises(ValueError):
        configure_hosted.configure_full(
            "demo.example.com", "full.example.com", "operator@example.com"
        )
    assert all(
        bool(target.read_bytes() == original)
        for target, original in zip((public, full), originals, strict=True)
    )


def test_full_setup_hash_failure_leaves_existing_public_configuration_untouched(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(configure_hosted, "ROOT", tmp_path)
    configure_hosted.configure("demo.example.com", "operator@example.com")
    original = (tmp_path / ".env.hosted").read_bytes()

    def fail(password):
        raise ValueError("Hashing unavailable")

    monkeypatch.setattr(configure_hosted, "bcrypt_hash", fail)
    with pytest.raises(ValueError, match="Hashing unavailable"):
        configure_hosted.configure_full(
            "other.example.com", "full.example.com", "operator@example.com"
        )
    assert bool((tmp_path / ".env.hosted").read_bytes() == original)
    assert not (tmp_path / ".env.hosted-full").exists()


def test_bcrypt_uses_private_stdin_without_network_or_password_arguments(monkeypatch, capsys):
    password = secrets.token_urlsafe(48)
    hashed = "$2b$14$" + secrets.token_hex(27)[:53]

    def run(command, **kwargs):
        assert "--plaintext" not in command and not bool(password in " ".join(command))
        assert command[command.index("--network") + 1] == "none"
        assert command[command.index("--pull") + 1] == "never"
        assert command[command.index("--algorithm") + 1] == "bcrypt"
        assert command[command.index("--bcrypt-cost") + 1] == "14"
        assert bool(kwargs["input"] == password + "\n") and kwargs["capture_output"]
        return subprocess.CompletedProcess(command, 0, hashed + "\n", "")

    monkeypatch.setattr(configure_hosted.subprocess, "run", run)
    assert bool(configure_hosted.bcrypt_hash(password) == hashed)
    assert capsys.readouterr() == ("", "")
