from __future__ import annotations

import copy
import re

from rca_core.models import FileChange, Hunk

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_unified_diff(text: str) -> list[FileChange]:
    files: list[FileChange] = []
    cur: FileChange | None = None
    hunk: Hunk | None = None
    body: list[str] = []

    def close_hunk() -> None:
        nonlocal hunk, body
        if hunk is not None and cur is not None:
            hunk.text = "\n".join(body)
            cur.hunks.append(hunk)
        hunk, body = None, []

    for line in text.splitlines():
        if line.startswith("diff --git "):
            close_hunk()
            parts = line.split(" ")
            old = parts[2][2:] if parts[2].startswith("a/") else parts[2]
            new = parts[3][2:] if parts[3].startswith("b/") else parts[3]
            cur = FileChange(path=new, old_path=old, change="modify")
            files.append(cur)
        elif cur is None:
            continue
        elif line.startswith("new file mode"):
            cur.change = "add"
        elif line.startswith("deleted file mode"):
            cur.change = "delete"
        elif line.startswith("--- "):
            p = line[4:]
            cur.old_path = "" if p == "/dev/null" else p[2:] if p.startswith("a/") else p
        elif line.startswith("+++ "):
            p = line[4:]
            cur.path = "" if p == "/dev/null" else p[2:] if p.startswith("b/") else p
            if not cur.path:
                cur.path = cur.old_path
        elif (m := _HUNK.match(line)):
            close_hunk()
            hunk = Hunk(
                old_path=cur.old_path or cur.path, new_path=cur.path,
                old_start=int(m.group(1)), old_len=int(m.group(2) or 1),
                new_start=int(m.group(3)), new_len=int(m.group(4) or 1), text="",
            )
        elif hunk is not None and line[:1] in (" ", "-", "+", "\\"):
            if not line.startswith("\\"):
                body.append(line)
    close_hunk()
    return files


def removed_old_lines(hunk: Hunk) -> list[int]:
    out: list[int] = []
    n = hunk.old_start
    for line in hunk.text.splitlines():
        if line.startswith("-"):
            out.append(n)
            n += 1
        elif line.startswith(" "):
            n += 1
    return out


def is_whitespace_only(hunk: Hunk) -> bool:
    def norm(prefix: str) -> list[str]:
        return ["".join(l[1:].split()) for l in hunk.text.splitlines() if l.startswith(prefix)]
    return norm("-") == norm("+")


def cap_hunks(files: list[FileChange], max_bytes: int) -> tuple[list[FileChange], bool]:
    """Keep hunks in order until the byte budget is spent. Returns (capped copy, truncated?)."""
    budget = max_bytes
    truncated = False
    out: list[FileChange] = []
    for f in files:
        fc = copy.deepcopy(f)
        kept: list[Hunk] = []
        for h in fc.hunks:
            if len(h.text) <= budget:
                kept.append(h)
                budget -= len(h.text)
            else:
                truncated = True
        fc.hunks = kept
        out.append(fc)
    return out, truncated
