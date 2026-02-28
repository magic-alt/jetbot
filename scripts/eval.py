"""Evaluation CLI: runs golden tests and reports accuracy metrics."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main():
    """Run golden test suite and print metrics summary."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/golden/", "-v", "--tb=short", "-q"],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
