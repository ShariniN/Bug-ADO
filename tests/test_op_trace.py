from rca_core.ado_client import AdoClient
from rca_core.cache import write_cache
from rca_core.operations.fetch import fetch
from rca_core.operations.trace import MAX_BLAME_PATHS, trace
from tests.ado_routes import commit_route, history_routes
from tests.conftest import FakeTransport
from tests.test_ado_client import ORG, PROJ, wi
from tests.test_op_fetch import BASE, HEAD, R, make_cfg, routes_pr_ok

C1, C2, C3 = "1" * 40, "2" * 40, "3" * 40
VERSIONS = [(BASE, "def calc(a):\n    b = None\n    return a + b\n"),   # state at base (== C3 content)
            (C2, "def calc(a):\n    b = None\n    return a + b\n"),
            (C1, "def calc(a):\n    b = 0\n    return a + b\n")]


def routes_with_culprit_pr(query_ids=(7,), refs=(("release/9.5", "r95"), ("release/10.1", "r101"))):
    r = routes_pr_ok()
    r.update(history_routes(R, "pay.py", VERSIONS, refs=list(refs),
                            merge_bases={(C2, "r95"): [C1], (C2, "r101"): [C2]}))
    r.update(commit_route(R, C2, author="Jane", subject="make b nullable"))
    r[("POST", "/pullrequestquery")] = {"results": [{C2: [{"pullRequestId": i} for i in query_ids]}]}
    r[("GET", "/pullrequests/7?")] = {"pullRequestId": 7, "title": "Make b nullable", "status": "completed",
                                      "repository": {"id": R, "name": "Acme.Web"}, "sourceRefName": "refs/heads/feature/x",
                                      "targetRefName": "refs/heads/main"}
    r[("GET", "/pullrequests/7/commits")] = {"value": []}
    r[("GET", "/pullrequests/7/workitems")] = {"value": [{"id": "500"}]}
    r[("GET", "/workitems?ids=500")] = {"value": [wi(500, "Task", "Nullable b", parent=600)]}
    r[("GET", "/workitems/500?")] = wi(500, "Task", "Nullable b", parent=600)
    r[("GET", "/workitems/600?")] = wi(600, "Feature", "Payroll v2")
    return r


def run(tmp_path, routes):
    cfg = make_cfg(tmp_path)
    client = AdoClient(ORG, PROJ, FakeTransport(routes))
    assert "error" not in fetch(100, cfg, client)
    return cfg, client, trace(100, cfg, client)


def test_trace_finds_culprit_pr_chain_and_versions(tmp_path):
    _, _, out = run(tmp_path, routes_with_culprit_pr())
    assert "error" not in out, out
    top = out["culprits"][0]
    assert top["sha"] == C2 and top["lines"] == 1 and top["author"] == "Jane"
    assert top["pr_id"] == 7 and [w["id"] for w in top["work_items"]] == [500]
    assert [w["type"] for w in top["parent_chain"]] == ["Feature"]
    assert top["release_branches"] == ["release/10.1"] and top["earliest_version"] == "10.1"
    assert any("Feature 600" in e for e in out["evidence"])


def test_trace_picks_earliest_pr_when_commit_is_in_several(tmp_path):
    _, _, out = run(tmp_path, routes_with_culprit_pr(query_ids=(900, 7)))
    assert out["culprits"][0]["pr_id"] == 7


def test_trace_without_pr_adds_note(tmp_path):
    r = routes_with_culprit_pr()
    r[("POST", "/pullrequestquery")] = {"results": [{}]}
    _, _, out = run(tmp_path, r)
    assert out["culprits"][0]["pr_id"] is None
    assert any("no merging pr" in n.lower() for n in out["confidence_notes"])


def test_trace_uses_configured_release_branch_pattern(tmp_path):
    r = routes_with_culprit_pr(refs=(("stable/11.0", "s11"),))
    r[("GET", f"/commits/{C2}/mergebases?otherCommitId=s11")] = {"value": [{"commitId": C2}]}
    cfg = make_cfg(tmp_path)
    cfg.release_branch_pattern = r"stable/(\d+\.\d+)"
    client = AdoClient(ORG, PROJ, FakeTransport(r))
    fetch(100, cfg, client)
    out = trace(100, cfg, client)
    assert out["culprits"][0]["release_branches"] == ["stable/11.0"] and out["culprits"][0]["earliest_version"] == "11.0"


def test_trace_without_repo_id_is_history_unavailable(tmp_path):
    cfg = make_cfg(tmp_path)
    write_cache(cfg, 100, {"files_full": [{"path": "p", "old_path": "p", "change": "modify", "hunks": []}], "repo_id": None, "base_sha": BASE, "repo": "x"})
    assert trace(100, cfg, AdoClient(ORG, PROJ, FakeTransport({})))["error"]["code"] == "history_unavailable"


def test_trace_without_fetch_errors(tmp_path):
    assert trace(999, make_cfg(tmp_path), AdoClient(ORG, PROJ, FakeTransport({})))["error"]["code"] == "fetch_first"


def test_trace_caps_blamed_paths_to_the_top_5(tmp_path):
    cfg = make_cfg(tmp_path)
    paths = [f"file{i}.py" for i in range(7)]
    files_full = [{"path": p, "old_path": p, "change": "modify",
                   "hunks": [{"old_path": p, "new_path": p, "old_start": 99, "old_len": 1,
                              "new_start": 99, "new_len": 1, "text": "-ghost"}]}
                  for p in paths]
    write_cache(cfg, 100, {"files_full": files_full, "repo_id": R, "base_sha": BASE, "repo": "x"})
    routes = {}
    for p in paths:
        routes.update(history_routes(R, p, VERSIONS))
    client = AdoClient(ORG, PROJ, FakeTransport(routes))
    out = trace(100, cfg, client)
    assert "error" not in out, out
    assert any(f"Blamed the {MAX_BLAME_PATHS} files" in n for n in out["confidence_notes"])
