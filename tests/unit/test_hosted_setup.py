import base64
import json
import os
import re
import secrets
import shutil
import stat
import subprocess

import pytest

from scripts import (
    configure_hosted,
    prepare_hosted_checks,
    prepare_hosted_full_checks,
    run_hosted_full_browser_checks,
)


def private_assert(condition, message="Private credential invariant failed"):
    # Assertion rewriting/fixture reprs must not disclose secrets on failure.
    if not condition:
        pytest.fail(message, pytrace=False)


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
    hash_password.calls = hashes
    return hash_password


def test_hosted_setup_generates_separate_private_secrets_and_preserves_them(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(configure_hosted, "ROOT", tmp_path)
    configure_hosted.configure("demo.example.com", "operator@example.com")
    target = tmp_path / ".env.hosted"
    content = target.read_text()
    values = dict(line.split("=", 1) for line in content.splitlines() if not line.startswith("#"))
    passwords = [values[name] for name in configure_hosted.SECRET_NAMES]
    private_assert(len(set(passwords)) == len(passwords))
    private_assert(all(len(password) >= 32 and len(set(password)) >= 16 for password in passwords))
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    configure_hosted.configure("demo.example.com", "operator@example.com")
    private_assert(target.read_text() == content)
    output = capsys.readouterr()
    private_assert(
        all(password not in output.out and password not in output.err for password in passwords)
    )


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
    private_assert(public.read_bytes() == original)
    values = configure_hosted.read_private(full)
    assert values["FULL_DOMAIN"] == "full.example.com"
    passwords = list(offline_bcrypt.calls[0]) + [
        values[name] for name in configure_hosted.FULL_SECRET_NAMES
    ]
    public_values = configure_hosted.read_private(public)
    deployment_secrets = [public_values[name] for name in configure_hosted.SECRET_NAMES] + [
        values[name] for name in configure_hosted.FULL_SECRET_NAMES
    ]
    private_assert(len(set(deployment_secrets)) == len(deployment_secrets))
    private_assert(all(len(value) >= 32 and len(set(value)) >= 16 for value in deployment_secrets))
    private_assert(len(values["FULL_BASIC_AUTH_PASSWORD"]) <= 72)
    private_assert(re.fullmatch(configure_hosted.BCRYPT_PATTERN, values["FULL_BASIC_AUTH_HASH"]))
    private_assert(
        "FULL_BASIC_AUTH_HASH='" + values["FULL_BASIC_AUTH_HASH"] + "'" in full.read_text()
    )
    assert stat.S_IMODE(full.stat().st_mode) == stat.S_IMODE(public.stat().st_mode) == 0o600
    configure_hosted.configure_full("demo.example.com", "full.example.com", "operator@example.com")
    private_assert(full.read_bytes() == full_original and public.read_bytes() == original)
    private_assert(
        len(offline_bcrypt.calls) == 1, "Existing gateway credentials must never be rotated"
    )
    output = capsys.readouterr()
    private_assert(
        all(
            not bool(secret in output.out or secret in output.err)
            for secret in passwords + deployment_secrets
        )
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
    assert list(tmp_path.iterdir()) == [] and offline_bcrypt.calls == []


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
    private_assert(public.read_bytes() == original)


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
    private_assert(
        all(
            bool(target.read_bytes() == original)
            for target, original in zip((public, full), originals, strict=True)
        )
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
    private_assert((tmp_path / ".env.hosted").read_bytes() == original)
    assert not (tmp_path / ".env.hosted-full").exists()


def test_bcrypt_uses_private_stdin_without_network_or_password_arguments(monkeypatch, capsys):
    password = secrets.token_urlsafe(48)
    hashed = "$2b$14$" + secrets.token_hex(27)[:53]

    def run(command, **kwargs):
        private_assert("--plaintext" not in command and password not in " ".join(command))
        assert command[command.index("--network") + 1] == "none"
        assert command[command.index("--pull") + 1] == "never"
        assert command[command.index("--algorithm") + 1] == "bcrypt"
        assert command[command.index("--bcrypt-cost") + 1] == "14"
        private_assert(kwargs["input"] == password + "\n" and kwargs["capture_output"])
        return subprocess.CompletedProcess(command, 0, hashed + "\n", "")

    monkeypatch.setattr(configure_hosted.subprocess, "run", run)
    private_assert(configure_hosted.bcrypt_hash(password) == hashed)
    assert capsys.readouterr() == ("", "")


def test_combined_compose_environment_preserves_bcrypt_and_separates_runtime_secrets(
    tmp_path, monkeypatch, offline_bcrypt
):
    root = configure_hosted.ROOT
    monkeypatch.setattr(configure_hosted, "ROOT", tmp_path)
    configure_hosted.configure_full("demo.example.com", "full.example.com", "operator@example.com")
    public_file, full_file = tmp_path / ".env.hosted", tmp_path / ".env.hosted-full"
    public = configure_hosted.read_private(public_file)
    full = configure_hosted.read_private(full_file)
    docker = shutil.which("docker")
    assert docker is not None

    def model(*filenames):
        result = subprocess.run(  # noqa: S603
            [
                docker,
                "compose",
                "--env-file",
                str(public_file),
                "--env-file",
                str(full_file),
                *(argument for filename in filenames for argument in ("-f", str(root / filename))),
                "config",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        private_assert(
            result.returncode == 0 and not result.stderr,
            "Private Compose interpolation must succeed without warnings",
        )
        return json.loads(result.stdout)["services"]

    shared = model("compose.hosted.yaml", "compose.hosted-gateway.yaml")
    writable = model("compose.hosted-full.yaml")
    # `compose config` escapes dollars for a subsequent Compose parse. The
    # actual single-dollar container value is also checked by the HTTPS suite.
    private_assert(
        shared["caddy"]["environment"]["FULL_BASIC_AUTH_HASH"]
        == full["FULL_BASIC_AUTH_HASH"].replace("$", "$$")
    )
    private_assert(shared["api"]["environment"]["SECRET_KEY"] == public["SECRET_KEY"])
    private_assert(writable["api"]["environment"]["SECRET_KEY"] == full["FULL_SECRET_KEY"])
    private_assert(
        public["PROOFOPS_RUNTIME_PASSWORD"] in shared["api"]["environment"]["DATABASE_URL"]
    )
    private_assert(full["FULL_RUNTIME_PASSWORD"] in writable["api"]["environment"]["DATABASE_URL"])
    for services in (shared, writable):
        private_assert(
            all(
                not bool(full["FULL_BASIC_AUTH_PASSWORD"] in json.dumps(service))
                for service in services.values()
            )
        )


@pytest.mark.parametrize("full", [False, True])
def test_isolated_hosted_preparation_preserves_shared_backend_images(
    tmp_path, monkeypatch, offline_bcrypt, full
):
    root = configure_hosted.ROOT
    (tmp_path / "deploy").mkdir()
    shutil.copyfile(root / "deploy/Caddyfile", tmp_path / "deploy/Caddyfile")
    monkeypatch.setattr(configure_hosted, "ROOT", tmp_path)
    if full:
        private = tmp_path / "artifacts/hosted-full/private"
        monkeypatch.setattr(prepare_hosted_full_checks, "ROOT", tmp_path)
        monkeypatch.setattr(prepare_hosted_full_checks, "PRIVATE", private)
        prepare_hosted_full_checks.prepare()
        variants = [
            ("compose.hosted.yaml", "images-public.json"),
            ("compose.hosted-full.yaml", "images-full.json"),
        ]
    else:
        private = tmp_path / "artifacts/hosted-security/private"
        prepare_hosted_checks.main()
        variants = [("compose.hosted.yaml", "images.json")]
    docker = shutil.which("docker")
    assert docker is not None
    env_files = [private / ".env.hosted"]
    if full:
        env_files.append(private / ".env.hosted-full")
    for filename, override in variants:
        result = subprocess.run(  # noqa: S603
            [
                docker,
                "compose",
                *(argument for path in env_files for argument in ("--env-file", str(path))),
                "--profile",
                "*",
                "-f",
                str(root / filename),
                "-f",
                str(private / override),
                "config",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        private_assert(result.returncode == 0, "Generated hosted Compose overrides must validate")
        # Keep assertion values free of the generated private environment.
        images = {
            name: service.get("image")
            for name, service in json.loads(result.stdout)["services"].items()
        }
        assert {images[name] for name in ("roles", "migrate", "api", "worker", "seed")} == {
            "proofops-backend"
        }
        assert images["web"] == "proofops-web"
        if filename == "compose.hosted.yaml":
            assert images["caddy"] == "proofops-caddy"
        else:
            assert "caddy" not in images


def test_browser_output_redacts_raw_and_encoded_credentials(tmp_path, monkeypatch, offline_bcrypt):
    monkeypatch.setattr(configure_hosted, "ROOT", tmp_path)
    monkeypatch.setattr(run_hosted_full_browser_checks, "PRIVATE", tmp_path)
    configure_hosted.configure_full("demo.example.com", "full.example.com", "operator@example.com")
    full = configure_hosted.read_private(tmp_path / ".env.hosted-full")
    application_password = secrets.token_urlsafe(48)
    configure_hosted.write_private(
        tmp_path / ".env.users", {"FULL_ADMIN_PASSWORD": application_password}
    )
    encoded = base64.b64encode(
        (full["FULL_BASIC_AUTH_USER"] + ":" + full["FULL_BASIC_AUTH_PASSWORD"]).encode()
    ).decode()
    sensitive = [application_password, encoded, *full.values()]
    output = run_hosted_full_browser_checks.redact_output(
        "prefix " + " ".join(sensitive) + " suffix"
    )
    private_assert(all(value not in output for value in sensitive))
    assert output.startswith("prefix ") and output.endswith(" suffix")
