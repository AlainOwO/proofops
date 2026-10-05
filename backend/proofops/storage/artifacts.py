import os
from pathlib import Path
from uuid import uuid4

from proofops.domain.common import bytes_digest


def put_artifact(root: Path, raw: bytes) -> str:
    hashed = bytes_digest(raw)
    directory = root / "exports"
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError("artifact directory escaped its configured root")
    target = directory / f"{hashed}.zip"
    if target.exists():
        if target.is_symlink() or bytes_digest(target.read_bytes()) != hashed:
            raise ValueError("artifact path is unsafe or corrupted")
        return hashed
    temporary = directory / (str(uuid4()) + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(target)
    return hashed


def get_artifact(root: Path, hashed: str) -> bytes:
    if len(hashed) != 64 or any(char not in "0123456789abcdef" for char in hashed):
        raise ValueError("invalid server artifact ID")
    target = root / "exports" / f"{hashed}.zip"
    if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("unsafe artifact path")
    if target.stat().st_size > 5_242_880:
        raise ValueError("artifact exceeds size cap")
    raw = target.read_bytes()
    if bytes_digest(raw) != hashed:
        raise ValueError("artifact integrity check failed")
    return raw
