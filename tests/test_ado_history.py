from rca_core.ado_client import AdoClient
from rca_core.ado_history import AdoHistory
from rca_core.diffparse import parse_unified_diff
from rca_core.git_forensics import blame_hunks
from tests.ado_routes import commit_route, diff_route, history_routes
from tests.conftest import FakeTransport

R = "repo-1"
# newest first: c4 unrelated edit, c3 whitespace reformat, c2 introduces 'b = None', c1 original
VERSIONS = [
    ("c4", "def calc(a):\n    b  =  None\n    return a + b  # v4\n"),
    ("c3", "def calc(a):\n    b  =  None\n    return a + b\n"),
    ("c2", "def calc(a):\n    b = None\n    return a + b\n"),
    ("c1", "def calc(a):\n    b = 0\n    return a + b\n"),
]


def hist(extra=None):
    routes = history_routes(R, "pay.py", VERSIONS, refs=[("release/9.5", "r95"), ("release/10.1", "r101"), ("main", "m")],
                            merge_bases={("c2", "r95"): ["c1"], ("c2", "r101"): ["c2"], ("c2", "m"): ["c2"]})
    routes.update(extra or {})
    return AdoHistory(AdoClient("https://dev.azure.com/acme", "Acme", FakeTransport(routes)), R)


def test_blame_ignores_whitespace_and_finds_introducing_commit():
    h = hist()
    assert h.blame_lines("c4", "pay.py", 1, 3) == {1: "c1", 2: "c2", 3: "c4"}
    assert h.history_truncated is False


def test_blame_hunks_uses_ado_history():
    h = hist()
    diff = "diff --git a/pay.py b/pay.py\n--- a/pay.py\n+++ b/pay.py\n@@ -2,1 +2,1 @@\n-    b  =  None\n+    b = 0\n"
    hunks = parse_unified_diff(diff)[0].hunks
    assert blame_hunks(h, "c4", hunks) == {"c2": 1}


def test_diff_builds_unified_diff_from_contents():
    h = hist({**diff_route(R, "c3", "c4", [("pay.py", "edit", None), ("new.txt", "add", None)]),
              ("TEXT", "items?path=new.txt&versionDescriptor.version=c4"): "hello\n"})
    files = parse_unified_diff(h.diff("c3", "c4"))
    assert [(f.path, f.change) for f in files] == [("pay.py", "modify"), ("new.txt", "add")]
    hk = files[0].hunks[0]
    assert hk.old_start == 1 and "-    return a + b" in hk.text and "+    return a + b  # v4" in hk.text
    assert files[1].hunks[0].text == "+hello"


def test_branches_containing_via_merge_bases():
    h = hist()
    assert h.branches_containing("c2", r"release/(\d+\.\d+)") == ["release/10.1"]


def test_history_truncated_flag():
    h = AdoHistory(AdoClient("https://dev.azure.com/acme", "Acme", FakeTransport(history_routes(R, "pay.py", VERSIONS[1:3]))), R, history_top=2)
    assert h.blame_lines("c3", "pay.py", 2, 2) == {2: "c2"}
    assert h.history_truncated is True


def test_commit_info_and_exists():
    h = hist(commit_route(R, "c2", author="Jane", subject="make b nullable"))
    assert h.commit_info("c2") == {"sha": "c2", "author": "Jane", "date": "2024-03-01", "subject": "make b nullable"}
    assert h.commit_exists("c2") is True
