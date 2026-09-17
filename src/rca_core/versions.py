from __future__ import annotations

import re


def parse_version(s: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", s))


def version_from_branch(branch: str, pattern: str) -> str | None:
    m = re.search(pattern, branch)
    return m.group(1) if m else None


def earliest_version(branches: list[str], pattern: str) -> str | None:
    versions = {v for b in branches if (v := version_from_branch(b, pattern))}
    if not versions:
        return None
    return min(versions, key=parse_version)
