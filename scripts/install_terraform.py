"""Install an optional, checksum-verified Terraform binary; never plans/applies AWS."""

import hashlib
import io
import json
import platform
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.16.5"


def fetch(url):
    if not url.startswith("https://releases.hashicorp.com/terraform/"):
        raise ValueError("only official pinned Terraform release URLs are allowed")
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        raw = response.read(100_000_001)
    if len(raw) > 100_000_000:
        raise ValueError("Terraform download exceeds size bound")
    return raw


def main():
    system = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}[platform.system()]
    arch = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "amd64"
    filename = f"terraform_{VERSION}_{system}_{arch}.zip"
    base = f"https://releases.hashicorp.com/terraform/{VERSION}/"
    checksums = fetch(base + f"terraform_{VERSION}_SHA256SUMS").decode()
    expected = next(
        line.split()[0]
        for line in checksums.splitlines()
        if line.split()[-1].lstrip("*") == filename
    )
    raw = fetch(base + filename)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Terraform archive checksum mismatch")
    name = "terraform.exe" if system == "windows" else "terraform"
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        binary = archive.read(name)
    target = ROOT / ".tools/bin" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(binary)
    target.chmod(0o755)
    inventory = json.loads((ROOT / "docs/tool_inventory.json").read_text())
    inventory = [item for item in inventory if item["tool"] != "terraform"]
    inventory.append(
        {
            "tool": "terraform",
            "version": VERSION,
            "platform": platform.system(),
            "architecture": arch,
            "source_url": base + filename,
            "archive_sha256": expected,
            "binary_sha256": hashlib.sha256(binary).hexdigest(),
        }
    )
    (ROOT / "docs/tool_inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    print(f"Installed checksum-verified Terraform {VERSION}; no cloud operations performed.")


if __name__ == "__main__":
    main()
