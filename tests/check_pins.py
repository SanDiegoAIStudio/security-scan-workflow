#!/usr/bin/env python3
"""Check that every `uses:` in GitHub Actions workflow files is pinned.

Usage: python3 tests/check_pins.py PATH...

PATH is a workflow file or a folder; a folder is searched for .yml and .yaml
files. A `uses:` that names another repository must end in an at sign, a
40-character hex commit id, and a trailing comment that starts with a version
such as `# v4.4.0`. A local ref that starts with `./` is allowed. A line that
carries a `# pin-exempt: example` comment is skipped (used by the example
caller, which shows a tag on purpose).

Exit codes: 0 all pinned, 1 something is not pinned, 2 bad usage.
Standard library only; it matches `uses:` lines and does not parse YAML.
"""

import re
import sys
from pathlib import Path

USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<rest>.*?)\s*$")
COMMIT_REF = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^#\s*v\d")
EXEMPT_COMMENT = re.compile(r"#\s*pin-exempt:\s*example\b")


def split_value_and_comment(rest):
    """Return (value, comment) for the text after `uses:`."""
    value, hash_mark, comment = rest.partition("#")
    value = value.strip().strip("'\"")
    return value, (hash_mark + comment).strip() if hash_mark else ""


def check_text(text):
    """Return a list of (line_number, uses_value) that are not pinned."""
    problems = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        match = USES_LINE.match(line)
        if not match:
            continue
        value, comment = split_value_and_comment(match.group("rest"))
        if not value or value.startswith("./"):
            continue
        if EXEMPT_COMMENT.search(comment):
            continue
        if COMMIT_REF.match(value) and VERSION_COMMENT.match(comment):
            continue
        problems.append((number, value))
    return problems


def collect_files(paths):
    files = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*") if p.suffix in (".yml", ".yaml")))
        elif path.is_file():
            files.append(path)
        else:
            return None
    return files


def main(argv):
    if not argv:
        print("usage: check_pins.py PATH...", file=sys.stderr)
        return 2
    files = collect_files(argv)
    if files is None:
        print("check_pins.py: a path does not exist", file=sys.stderr)
        return 2
    failed = False
    for path in files:
        for number, value in check_text(path.read_text(encoding="utf-8")):
            print(f"{path}:{number}: not pinned: {value}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
