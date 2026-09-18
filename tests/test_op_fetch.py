import json
from pathlib import Path

from rca_core.ado_client import AdoClient
from rca_core.config import load_config
from rca_core.errors import RcaError
from rca_core.operations.fetch import fetch
from tests.ado_routes import commit_route, diff_route, history_routes, repo_routes
from tests.conftest import FakeTransport
from tests.test_ado_client import ORG, PROJ, wi

R = "repo-1"
BASE, HEAD, MERGE, TARGET = "b" * 40, "h" * 40, "m" * 40, "t" * 40
OLD = "def calc(a):\n    b = None\n    return a + b\n"
NEW = "def calc(a):\n    b = 0\n    return a + b\n"


def make_cfg(tmp_path):
    (tmp_path / "cfg.toml").write_text('[auth]\nmode = "pat"\n', encoding="utf-8")
    cfg = load_config(user_path=tmp_path / "cfg.toml", env={"ADO_PAT": "x"})
    cfg.org_url, cfg.project = ORG, PROJ
    cfg.home = tmp_path / ".rca"
    return cfg


def bug_route(prs=(("repo-1", 55),)):
    w = wi(100, "Bug", "Crash", prs=list(prs))
    w["fields"].update({"System.AreaPath": "Acme\\Payroll", "System.Tags": "client-x; urgent",
                        "Microsoft.VSTS.TCM.ReproSteps": "<p>Open payslip</p>", "Custom.Environment": "UAT"})
    return {("GET", "/workitems/100?"): w}


def pr_routes(source_sha=HEAD, target_sha=TARGET, merge_sha=MERGE, pr_id=55):
    # Repo-scoped keys: a bare f"/pullrequests/{pr_id}?" is also a substring of the org-level
    # pr_repo_id URL ({org}/_apis/git/pullrequests/{pr_id}?...), and FakeTransport answers the
    # first substring match in insertion order, so an unscoped key here would silently steal
    # org-level lookups too (see test_fetch_explicit_pr_id_resolves_repo_at_project_level).
    return {
        ("GET", f"/repositories/{R}/pullrequests/{pr_id}?"): {
            "pullRequestId": pr_id, "title": "Fix null total", "status": "completed",
            "repository": {"id": R, "name": "Acme.Web"},
            "sourceRefName": "refs/heads/bugfix/1", "targetRefName": "refs/heads/main",
            "lastMergeSourceCommit": {"commitId": source_sha}, "lastMergeTargetCommit": {"commitId": target_sha},
            "lastMergeCommit": {"commitId": merge_sha}},
        ("GET", f"/repositories/{R}/pullrequests/{pr_id}/commits"): {"value": []},
        ("GET", f"/repositories/{R}/pullrequests/{pr_id}/workitems"): {"value": []},
    }


def diff_routes(base=BASE, head=HEAD):
    return {**diff_route(R, base, head, [("pay.py", "edit", None)]),
            ("TEXT", f"items?path=pay.py&versionDescriptor.version={base}"): OLD,
            ("TEXT", f"items?path=pay.py&versionDescriptor.version={head}"): NEW}


def routes_pr_ok():
    r = {**bug_route(), **pr_routes(), **diff_routes(), **commit_route(R, HEAD)}
    r[("GET", f"/commits/{HEAD}/mergebases?otherCommitId={TARGET}")] = {"value": [{"commitId": BASE}]}
    r[("GET", f"/commits/{TARGET}/mergebases?otherCommitId={HEAD}")] = {"value": [{"commitId": BASE}]}
    return r


def test_fetch_from_linked_pr_uses_ado_diff_and_caches(tmp_path):
    cfg = make_cfg(tmp_path)
    out = fetch("100", cfg, AdoClient(ORG, PROJ, FakeTransport(routes_pr_ok())))
    assert "error" not in out, out
    assert out["source"] == "pr" and out["repo"] == "Acme.Web" and out["repo_id"] == R
    assert out["base_sha"] == BASE and out["head_sha"] == HEAD
    assert out["bug"]["repro_steps"] == "Open payslip" and out["bug"]["extra"] == {"Custom.Environment": "UAT"}
    assert out["files"][0]["path"] == "pay.py" and "-    b = None" in out["files"][0]["hunks"][0]["text"]
    cached = json.loads((cfg.cache_dir / "100.json").read_text(encoding="utf-8"))
    assert cached["repo_id"] == R and cached["trace"] is None and cached["files_full"][0]["hunks"]


def test_fetch_accepts_work_item_url(tmp_path):
    out = fetch("https://dev.azure.com/acme/Acme/_workitems/edit/100", make_cfg(tmp_path), AdoClient(ORG, PROJ, FakeTransport(routes_pr_ok())))
    assert out["bug_id"] == 100 and out["resolved"]["how"] == "url"


def test_fetch_missing_source_falls_back_to_merge_commit(tmp_path):
    r = routes_pr_ok()

    def raise_not_found(_):
        raise RcaError("not_found", "404", "")

    # NOTE: brief specified key f"/commits/{HEAD}?" here, but that is a distinct dict key from the one
    # commit_route(R, HEAD) already registered (f"/repositories/{R}/commits/{HEAD}?"); FakeTransport matches
    # the first substring hit in insertion order, so the brief's key never shadows the earlier one and the
    # override silently has no effect. Using the same key as commit_route actually replaces it in place,
    # matching the brief's own note that this route must raise not_found so commit_exists() returns False.
    r[("GET", f"/repositories/{R}/commits/{HEAD}?")] = raise_not_found
    r.update(commit_route(R, MERGE, parents=[BASE]))
    r.update(diff_routes(BASE, MERGE))
    out = fetch(100, make_cfg(tmp_path), AdoClient(ORG, PROJ, FakeTransport(r)))
    assert "error" not in out, out
    assert out["head_sha"] == MERGE and out["base_sha"] == BASE


def test_fetch_explicit_pr_id_resolves_repo_at_project_level(tmp_path):
    r = {**bug_route(prs=()), **pr_routes(pr_id=77), **diff_routes(), **commit_route(R, HEAD),
         ("GET", "/_apis/git/pullrequests/77?"): {"pullRequestId": 77, "repository": {"id": R}},
         ("GET", f"/commits/{TARGET}/mergebases?otherCommitId={HEAD}"): {"value": [{"commitId": BASE}]}}
    t = FakeTransport(r)
    out = fetch(100, make_cfg(tmp_path), AdoClient(ORG, PROJ, t), pr_id=77)
    assert out["pr"]["id"] == 77 and out["source"] == "pr"
    assert any("/_apis/git/pullrequests/77?" in c[1] and "/repositories/" not in c[1] for c in t.calls)


def test_fetch_no_pr_and_no_repo_is_no_fix_source(tmp_path):
    r = {**bug_route(prs=())}
    out = fetch(100, make_cfg(tmp_path), AdoClient(ORG, PROJ, FakeTransport(r)), cwd=tmp_path)
    assert out["error"]["code"] == "no_fix_source"


def test_fetch_local_branch_fallback(git_repo, tmp_path):
    repo, sha = git_repo
    repo.run("checkout", "-q", "bugfix/1")
    repo.run("remote", "add", "origin", "https://dev.azure.com/acme/Acme/_git/Acme.Web")
    r = {**bug_route(prs=()), **repo_routes(R, "Acme.Web"),
         ("GET", "/_apis/git/pullrequests?searchCriteria.sourceRefName=refs/heads/bugfix/1"): {"value": []}}
    out = fetch(100, make_cfg(tmp_path), AdoClient(ORG, PROJ, FakeTransport(r)), cwd=repo.path)
    assert "error" not in out, out
    assert out["source"] == "branch" and out["repo_id"] == R and out["base_sha"] == sha["ws"] and out["head_sha"] == sha["fix_src"]
    assert out["files"][0]["path"] == "pay.py"


def test_fetch_local_branch_on_default_branch_is_no_fix_source(git_repo, tmp_path):
    repo, sha = git_repo
    r = {**bug_route(prs=()), ("GET", "/_apis/git/pullrequests?searchCriteria.sourceRefName=refs/heads/main"): {"value": []}}
    out = fetch(100, make_cfg(tmp_path), AdoClient(ORG, PROJ, FakeTransport(r)), cwd=repo.path)
    assert out["error"]["code"] == "no_fix_source"


def test_cache_keeps_uncapped_hunks_when_output_is_capped(tmp_path, monkeypatch):
    import rca_core.operations.fetch as fetch_mod
    monkeypatch.setattr(fetch_mod, "FETCH_CAP_BYTES", 5)
    cfg = make_cfg(tmp_path)
    out = fetch(100, cfg, AdoClient(ORG, PROJ, FakeTransport(routes_pr_ok())))
    assert out["truncated"] is True and out["files"][0]["hunks"] == []
    assert json.loads((cfg.cache_dir / "100.json").read_text(encoding="utf-8"))["files_full"][0]["hunks"]
