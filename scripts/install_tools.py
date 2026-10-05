"""Install checksum-verified, pinned Conftest/k6 binaries into .tools/bin."""

import hashlib
import io
import json
import platform
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = {"conftest": "0.71.0", "k6": "2.3.0"}


def fetch(url: str) -> bytes:
    if not url.startswith("https://github.com/"):
        raise ValueError("tool downloads must use a pinned official GitHub release")
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        value = response.read(100_000_001)
    if len(value) > 100_000_000:
        raise ValueError("tool download exceeds size cap")
    return value


def main():
    system = platform.system()
    arch = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "amd64"
    if system not in {"Darwin", "Linux", "Windows"}:
        raise SystemExit("Unsupported local tool platform; use the pinned Docker images.")
    directory = ROOT / ".tools/bin"
    directory.mkdir(parents=True, exist_ok=True)
    inventory = []
    for tool, version in VERSIONS.items():
        windows = system == "Windows"
        suffix = ".exe" if windows else ""
        if tool == "conftest":
            architecture = "arm64" if arch == "arm64" else "x86_64"
            filename = (
                f"conftest_{version}_{system}_{architecture}.{'zip' if windows else 'tar.gz'}"
            )
            base = f"https://github.com/open-policy-agent/conftest/releases/download/v{version}/"
            checksum_name = "checksums.txt"
        else:
            os_name = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}[system]
            filename = f"k6-v{version}-{os_name}-{arch}.{'zip' if system != 'Linux' else 'tar.gz'}"
            base = f"https://github.com/grafana/k6/releases/download/v{version}/"
            checksum_name = f"k6-v{version}-checksums.txt"
        checksums = fetch(base + checksum_name).decode()
        expected = next(
            (
                line.split()[0]
                for line in checksums.splitlines()
                if line.split()[-1].lstrip("*") == filename
            ),
            None,
        )
        if expected is None:
            raise ValueError("archive is absent from the official checksum list")
        raw = fetch(base + filename)
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise ValueError("tool archive checksum mismatch")
        if filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                matches = [name for name in archive.namelist() if Path(name).name == tool + suffix]
                if len(matches) != 1:
                    raise ValueError("expected exactly one tool binary")
                binary = archive.read(matches[0])
        else:
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
                matches = [
                    member
                    for member in archive.getmembers()
                    if Path(member.name).name == tool + suffix and member.isfile()
                ]
                if len(matches) != 1:
                    raise ValueError("expected exactly one regular tool binary")
                stream = archive.extractfile(matches[0])
                if stream is None:
                    raise ValueError("tool binary is unreadable")
                binary = stream.read()
        destination = directory / (tool + suffix)
        destination.write_bytes(binary)
        destination.chmod(0o755)
        inventory.append(
            {
                "tool": tool,
                "version": version,
                "platform": system,
                "architecture": arch,
                "source_url": base + filename,
                "archive_sha256": actual,
                "binary_sha256": hashlib.sha256(binary).hexdigest(),
            }
        )
        print(f"Installed checksum-verified {tool} {version} in .tools/bin", flush=True)
    (ROOT / "docs/tool_inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")


if __name__ == "__main__":
    main()
