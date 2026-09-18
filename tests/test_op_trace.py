import pytest

pytest.skip("rewritten in v2 Task 5", allow_module_level=True)

from rca_core.ado_client import AdoClient
from rca_core.operations.fetch import fetch
from rca_core.operations.trace import trace
from tests.conftest import FakeTransport
from tests.test_ado_client import ORG, PROJ, wi
from tests.test_op_fetch import make_cfg, pr_routes


def routes_with_culprit_pr(sha):
    r = pr_routes(sha)
    r[("POST", "/pullrequestquery")] = {"results": [{sha["culprit"]: [{"pullRequestId": 7}]}]}
    r[("GET", "/pullrequests/7?")] = {
        "pullRequestId": 7, "title": "Make b nullable", "status": "completed",
        "repository": {"id": "repo-1", "name": "Acme.Web"},
        "sourceRefName": "refs/heads/feature/x", "targetRefName": "refs/heads/main",
        "lastMergeSourceCommit": {"commitId": sha["culprit"]}, "lastMergeTargetCommit": {"commitId": sha["c1"]},
        "lastMergeCommit": {"commitId": sha["culprit"]}}
    r[("GET", "/pullrequests/7/commits")] = {"value": []}
    r[("GET", "/pullrequests/7/workitems")] = {"value": [{"id": "500"}]}
    r[("GET", "/workitems?ids=500")] = {"value": [wi(500, "Task", "Nullable b", parent=600)]}
    r[("GET", "/workitems/500?")] = wi(500, "Task", "Nullable b", parent=600)
    r[("GET", "/workitems/600?")] = wi(600, "Feature", "Payroll v2")
    return r


def test_trace_finds_culprit_pr_chain_and_versions(git_repo, tmp_path):
    repo, sha = git_repo
    cfg = make_cfg(tmp_path, repo)
    client = AdoClient(ORG, PROJ, FakeTransport(routes_with_culprit_pr(sha)))
    assert "error" not in fetch(100, cfg, client)
    out = trace(100, cfg, client)
    assert "error" not in out, out
    top = out["culprits"][0]
    assert top["sha"] == sha["culprit"] and top["lines"] == 1
    assert top["pr_id"] == 7 and top["pr_title"] == "Make b nullable"
    assert [w["id"] for w in top["work_items"]] == [500]
    assert [w["type"] for w in top["parent_chain"]] == ["Feature"]
    assert "release/10.1" in top["release_branches"] and "release/9.5" not in top["release_branches"]
    assert top["earliest_version"] == "10.1"
    assert any("release/10.1" in e for e in out["evidence"])
    assert any("Feature 600" in e for e in out["evidence"])


def test_trace_falls_back_to_merge_history_when_query_empty(git_repo, tmp_path):
    repo, sha = git_repo
    cfg = make_cfg(tmp_path, repo)
    r = pr_routes(sha)
    r[("POST", "/pullrequestquery")] = {"results": [{}]}
    client = AdoClient(ORG, PROJ, FakeTransport(r))
    fetch(100, cfg, client)
    out = trace(100, cfg, client)
    # culprit was committed directly (no merge), so no PR either way; still ranked and versioned
    assert out["culprits"][0]["pr_id"] is None
    assert out["culprits"][0]["earliest_version"] == "10.1"
    assert any("no merging pr" in n.lower() for n in out["confidence_notes"])


def test_trace_without_fetch_errors(git_repo, tmp_path):
    repo, sha = git_repo
    cfg = make_cfg(tmp_path, repo)
    out = trace(999, cfg, AdoClient(ORG, PROJ, FakeTransport({})))
    assert out["error"]["code"] == "fetch_first"


def test_trace_picks_earliest_pr_when_commit_is_in_several(git_repo, tmp_path):
    repo, sha = git_repo
    cfg = make_cfg(tmp_path, repo)
    r = routes_with_culprit_pr(sha)
    r[("POST", "/pullrequestquery")] = {"results": [{sha["culprit"]: [{"pullRequestId": 900}, {"pullRequestId": 7}]}]}
    client = AdoClient(ORG, PROJ, FakeTransport(r))
    fetch(100, cfg, client)
    out = trace(100, cfg, client)
    assert "error" not in out, out
    assert out["culprits"][0]["pr_id"] == 7


def test_trace_notes_pure_addition_fallback(git_repo, tmp_path):
    from rca_core.cache import write_cache
    repo, sha = git_repo
    cfg = make_cfg(tmp_path, repo)
    r = pr_routes(sha)
    r[("POST", "/pullrequestquery")] = {"results": [{}]}
    client = AdoClient(ORG, PROJ, FakeTransport(r))
    fetch(100, cfg, client)
    write_cache(cfg, 100, {"files_full": [{"path": "pay.py", "old_path": "pay.py", "change": "modify", "hunks": [
        {"old_path": "pay.py", "new_path": "pay.py", "old_start": 2, "old_len": 0, "new_start": 3, "new_len": 1, "text": "+    c = 1"}]}]})
    out = trace(100, cfg, client)
    assert any("only added lines" in n for n in out["confidence_notes"])
    assert out["culprits"]


def test_trace_uses_configured_release_branch_pattern(git_repo, tmp_path):
    repo, sha = git_repo
    repo.run("branch", "stable/11.0", sha["culprit"])
    cfg = make_cfg(tmp_path, repo)
    cfg.release_branch_pattern = r"stable/(\d+\.\d+)"
    r = pr_routes(sha)
    r[("POST", "/pullrequestquery")] = {"results": [{}]}
    client = AdoClient(ORG, PROJ, FakeTransport(r))
    fetch(100, cfg, client)
    out = trace(100, cfg, client)
    top = out["culprits"][0]
    assert top["release_branches"] == ["stable/11.0"]
    assert top["earliest_version"] == "11.0"
