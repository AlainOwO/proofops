import os
import stat

import pytest

from scripts import configure_hosted


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
