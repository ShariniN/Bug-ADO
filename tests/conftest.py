from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rca_core.git_forensics import GitRepo


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path) -> tuple[GitRepo, dict[str, str]]:
    """History (main is left at `ws` so merge-base tests are meaningful):
    c1 (release/9.5): pay.py with total = a + b
    culprit (release/10.1): changes 'b = 0' -> 'b = None'   <- the bug
    ws (main): whitespace-only reformat of the same line
    fix_src (bugfix/1): restores b = 0
    fix (merged): merge commit 'Merged PR 42: fix null total' of bugfix/1 on branch `merged`
    """
    d = tmp_path / "repo"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    f = d / "pay.py"
    f.write_text("def calc(a):\n    b = 0\n    return a + b\n", encoding="utf-8")
    _git(d, "add", "."); _git(d, "commit", "-q", "-m", "c1 initial")
    c1 = _git(d, "rev-parse", "HEAD")
    _git(d, "branch", "release/9.5")

    f.write_text("def calc(a):\n    b = None\n    return a + b\n", encoding="utf-8")
    _git(d, "commit", "-q", "-am", "culprit: make b nullable")
    culprit = _git(d, "rev-parse", "HEAD")
    _git(d, "branch", "release/10.1")

    f.write_text("def calc(a):\n    b  =  None\n    return a + b\n", encoding="utf-8")
    _git(d, "commit", "-q", "-am", "ws: reformat")
    ws = _git(d, "rev-parse", "HEAD")

    _git(d, "checkout", "-q", "-b", "bugfix/1")
    f.write_text("def calc(a):\n    b = 0\n    return a + b\n", encoding="utf-8")
    _git(d, "commit", "-q", "-am", "fix null total")
    fix_src = _git(d, "rev-parse", "HEAD")
    _git(d, "checkout", "-q", "main")
    _git(d, "checkout", "-q", "-b", "merged")
    _git(d, "merge", "-q", "--no-ff", "-m", "Merged PR 42: fix null total", "bugfix/1")
    fix = _git(d, "rev-parse", "HEAD")
    _git(d, "checkout", "-q", "main")

    return GitRepo(d), {"c1": c1, "culprit": culprit, "ws": ws, "fix_src": fix_src, "fix": fix}


class FakeTransport:
    """Routes (METHOD, url substring) -> response json. Records every call."""

    def __init__(self, routes: dict[tuple[str, str], object]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, object]] = []

    def request(self, method: str, url: str, json: object = None, content_type: str = "application/json") -> object:
        self.calls.append((method, url, json))
        for (m, sub), resp in self.routes.items():
            if m == method and sub in url:
                return resp(json) if callable(resp) else resp
        raise AssertionError(f"unrouted {method} {url}")
