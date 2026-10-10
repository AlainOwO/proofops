"""Run the isolated full-host browser suite with credential-safe output."""

import os
import shutil
import subprocess

from scripts.configure_hosted import read_private
from scripts.prepare_hosted_full_checks import PRIVATE, ROOT


def redact_output(output: str) -> str:
    values = {}
    for filename in (".env.hosted", ".env.hosted-full", ".env.users"):
        values.update(read_private(PRIVATE / filename))
    for value in sorted(filter(None, values.values()), key=len, reverse=True):
        output = output.replace(value, "<private>")
    return output


def main() -> None:
    node = shutil.which("node")
    if node is None:
        raise SystemExit("Node is required for browser checks.")
    try:
        result = subprocess.run(
            [
                node,
                "--require",
                "../tests/hosted_browser/loopback.cjs",
                "node_modules/@playwright/test/cli.js",
                "test",
                "--config",
                "playwright.hosted-full.config.ts",
            ],
            cwd=ROOT / "frontend",
            env=os.environ
            | {"HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "", "NO_PROXY": "*"},
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
        output = redact_output(result.stdout + result.stderr)
        (ROOT / "artifacts/hosted-full/browser.txt").write_text(output)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise SystemExit(
            "Browser checks did not complete; private output was not printed."
        ) from None
    print(output)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
