#!/usr/bin/env python3
"""Inspect native Python dependencies without importing them or changing macOS security policy."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def native_paths(environment: Path) -> list[Path]:
    """Include the interpreter and extension libraries, including wheel-private dylibs."""
    return sorted({path for path in environment.rglob("*")
                   if path.is_file() and (path.suffix in (".so", ".dylib")
                                          or path.parent == environment / "bin")})


def check(environment: Path) -> int:
    if sys.platform != "darwin":
        return 0
    paths = native_paths(environment)
    for offset in range(0, len(paths), 200):
        result = subprocess.run(
            ["/usr/bin/xattr", "-p", "com.apple.quarantine",
             *(str(path) for path in paths[offset:offset + 200])],
            capture_output=True, text=True, check=False,
        )
        # xattr emits absent-attribute diagnostics on stderr, and only found values on stdout.
        if result.stdout.strip():
            print("Quarantined Python native dependencies; no imports attempted:\n"
                  + result.stdout, file=sys.stderr)
            return 1
        errors = [line for line in result.stderr.splitlines()
                  if "No such xattr: com.apple.quarantine" not in line]
        if errors:
            print("Cannot inspect Python native dependencies:\n" + "\n".join(errors),
                  file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(check(Path(sys.argv[1]).absolute()))
