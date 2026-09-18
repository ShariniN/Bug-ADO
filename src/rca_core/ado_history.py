from __future__ import annotations

import difflib
import re
from collections import Counter

from rca_core.ado_client import AdoClient
from rca_core.errors import RcaError

BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".dll", ".exe", ".pdf", ".zip", ".woff", ".woff2", ".ttf", ".snk", ".pfx"}
_TRIVIAL = re.compile(r"^[{}()\[\];,]*$")


def _key(line: str) -> str:
    return "".join(line.split())


def _blameable(key: str) -> bool:
    return len(key) >= 4 and not _TRIVIAL.match(key)


class AdoHistory:
    """History questions answered from the Azure DevOps REST API. Emulates `git blame -w` from file versions."""

    def __init__(self, client: AdoClient, repo_id: str, history_top: int = 100) -> None:
        self.client, self.repo_id, self.history_top = client, repo_id, history_top
        self._lines: dict[tuple[str, str], list[str] | None] = {}
        self._hist: dict[tuple[str, str], list[str]] = {}
        self.history_truncated = False
        self.paths_truncated = False
        self.unattributed = 0
        self._refs: list[dict] | None = None

    def file_lines(self, sha: str, path: str) -> list[str] | None:
        k = (sha, path)
        if k not in self._lines:
            text = self.client.get_item_text(self.repo_id, path, sha)
            self._lines[k] = None if text is None else text.splitlines()
        return self._lines[k]

    def diff(self, base: str, head: str, max_paths: int = 50) -> str:
        out: list[str] = []
        changes = self.client.changed_paths(self.repo_id, base, head)
        if len(changes) > max_paths:
            changes = changes[:max_paths]
            self.paths_truncated = True
        for ch in changes:
            if any(ch["path"].lower().endswith(e) for e in BINARY_EXT):
                continue
            old = None if ch["change"] == "add" else self.file_lines(base, ch["old_path"])
            new = None if ch["change"] == "delete" else self.file_lines(head, ch["path"])
            a, b = old or [], new or []
            body = "\n".join(difflib.unified_diff(a, b, fromfile=f"a/{ch['old_path']}" if old is not None else "/dev/null",
                                                  tofile=f"b/{ch['path']}" if new is not None else "/dev/null", lineterm="", n=3))
            if not body:
                continue
            mode = "new file mode 100644\n" if ch["change"] == "add" else "deleted file mode 100644\n" if ch["change"] == "delete" else ""
            out.append(f"diff --git a/{ch['old_path']} b/{ch['path']}\n{mode}{body}")
        return "\n".join(out) + ("\n" if out else "")

    def path_history(self, path: str, sha: str) -> list[str]:
        k = (sha, path)
        if k not in self._hist:
            self._hist[k] = self.client.path_history(self.repo_id, path, sha, self.history_top)
        return self._hist[k]

    def blame_lines(self, sha: str, path: str, start: int, end: int) -> dict[int, str]:
        base = self.file_lines(sha, path)
        hist = self.path_history(path, sha) if base is not None else []
        if not base or not hist:
            return {}
        counts = Counter(_key(l) for l in base)
        # content at hist[0] equals content at sha (base), so no fetch needed to seed it
        keysets: dict[str, set[str]] = {hist[0]: {k for k in counts}}

        def keys(commit: str) -> set[str]:
            if commit not in keysets:
                ls = self.file_lines(commit, path)
                keysets[commit] = {_key(l) for l in ls} if ls else set()
            return keysets[commit]

        result: dict[int, str] = {}
        for n in range(max(1, start), min(end, len(base)) + 1):
            key = _key(base[n - 1])
            if not key:
                continue
            if not _blameable(key) or counts[key] != 1:
                self.unattributed += 1
                continue
            lo, hi = 0, len(hist) - 1  # invariant: key present at hist[lo]
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if key in keys(hist[mid]):
                    lo = mid
                else:
                    hi = mid - 1
            result[n] = hist[lo]
            if lo == len(hist) - 1 and len(hist) >= self.history_top:
                self.history_truncated = True
        return result

    def commit_info(self, sha: str) -> dict:
        c = self.client.get_commit(self.repo_id, sha)
        return {k: c[k] for k in ("sha", "author", "date", "subject")}

    def commit_exists(self, sha: str) -> bool:
        try:
            self.client.get_commit(self.repo_id, sha)
            return True
        except RcaError as e:
            if e.code == "not_found":
                return False
            raise

    def merge_base(self, a: str, b: str) -> str | None:
        mbs = self.client.merge_bases(self.repo_id, a, b)
        return mbs[0] if mbs else None

    def branches_containing(self, sha: str, pattern: str) -> list[str]:
        if self._refs is None:
            self._refs = self.client.get_refs(self.repo_id, "heads/")
        names: list[str] = []
        for ref in self._refs:
            if not re.search(pattern, ref["name"]):
                continue
            if ref["sha"] == sha or sha in self.client.merge_bases(self.repo_id, sha, ref["sha"]):
                names.append(ref["name"])
        return names
