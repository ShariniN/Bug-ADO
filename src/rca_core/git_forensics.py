from __future__ import annotations

import re
import subprocess
from pathlib import Path

from rca_core.diffparse import is_whitespace_only, removed_old_lines
from rca_core.errors import RcaError
from rca_core.models import Hunk

_PORCELAIN_HEAD = re.compile(r"^([0-9a-f]{40}) (\d+) (\d+)(?: (\d+))?$")
_MERGED_PR = re.compile(r"Merged PR (\d+)")


class GitRepo:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def run(self, *args: str, check: bool = True) -> str:
        proc = subprocess.run(["git", *args], cwd=self.path, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if check and proc.returncode != 0:
            raise RcaError("git_failed", f"git {' '.join(args[:2])} failed: {proc.stderr.strip()[:300]}",
                           f"Run the command manually in {self.path} to see the full error.")
        return proc.stdout.rstrip("\n")

    def fetch(self) -> None:
        self.run("fetch", "--quiet", "--prune", "origin", check=False)

    def rev_parse(self, ref: str) -> str:
        return self.run("rev-parse", "--verify", f"{ref}^{{commit}}")

    def has_ref(self, ref: str) -> bool:
        return subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=self.path,
                              capture_output=True).returncode == 0

    def current_branch(self) -> str:
        return self.run("rev-parse", "--abbrev-ref", "HEAD")

    def merge_base(self, a: str, b: str) -> str:
        return self.run("merge-base", a, b)

    def diff(self, base: str, head: str) -> str:
        return self.run("diff", "--unified=3", "--no-color", "--find-renames", base, head)

    def blame_lines(self, sha: str, path: str, start: int, end: int) -> dict[int, str]:
        """Map old-file line number -> commit sha, for lines start..end of `path` at `sha`."""
        out = self.run("blame", "--porcelain", "-w", "-M", "-C", "-L", f"{start},{end}", sha, "--", path, check=False)
        result: dict[int, str] = {}
        for line in out.splitlines():
            m = _PORCELAIN_HEAD.match(line)
            if m:
                result[int(m.group(3))] = m.group(1)
        return result

    def commit_info(self, sha: str) -> dict[str, str]:
        raw = self.run("log", "-1", "--format=%H%x1f%an%x1f%as%x1f%s", sha)
        h, an, date, subject = raw.split("\x1f", 3)
        return {"sha": h, "author": an, "date": date, "subject": subject.strip()[:120]}

    def branches_containing(self, sha: str) -> list[str]:
        out = self.run("branch", "-a", "--contains", sha, "--format=%(refname:short)", check=False)
        names = []
        for b in out.splitlines():
            b = b.strip()
            if b.startswith("origin/"):
                b = b[len("origin/"):]
            if b and b != "HEAD" and b not in names:
                names.append(b)
        return names

    def _is_ancestor(self, a: str, b: str) -> bool:
        return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=self.path,
                              capture_output=True).returncode == 0

    def merged_pr_id_from_history(self, sha: str, target_ref: str) -> int | None:
        """Find the first-parent merge on target_ref that brought `sha` in (sha is NOT an ancestor of the
        merge's first parent but IS an ancestor of its second parent). Return its 'Merged PR N' id."""
        out = self.run("log", "--first-parent", "--ancestry-path", "--reverse", "--merges",
                       "--format=%H%x1f%s", f"{sha}..{target_ref}", check=False)
        for line in out.splitlines():
            merge_sha, subject = line.split("\x1f", 1)
            if self._is_ancestor(sha, f"{merge_sha}^1"):
                continue  # already on the mainline before this merge; not the one that introduced it
            if self._is_ancestor(sha, f"{merge_sha}^2"):
                m = _MERGED_PR.search(subject)
                return int(m.group(1)) if m else None
        return None


def blame_hunks(repo: GitRepo, base_sha: str, hunks: list[Hunk]) -> dict[str, int]:
    """Culprit sha -> number of removed (pre-fix) lines authored by it. Whitespace-only hunks are skipped."""
    counts: dict[str, int] = {}
    for h in hunks:
        if not h.old_path or is_whitespace_only(h):
            continue
        lines = removed_old_lines(h)
        if not lines:
            # pure addition: the line the insertion follows plus one on each side
            lines = list(range(max(1, h.old_start - 1), h.old_start + 2))
        blamed = repo.blame_lines(base_sha, h.old_path, min(lines), max(lines))
        for n in lines:
            sha = blamed.get(n)
            if sha:
                counts[sha] = counts.get(sha, 0) + 1
    return counts
