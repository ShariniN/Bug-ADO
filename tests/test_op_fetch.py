import json

from rca_core.ado_client import AdoClient
from rca_core.config import load_config
from rca_core.operations.fetch import fetch
from tests.conftest import FakeTransport
from tests.test_ado_client import ORG, PROJ, wi


def make_cfg(tmp_path, repo):
    cfg = load_config(user_path=tmp_path / "cfg.toml", env={"ADO_PAT": "x"})
    cfg.org_url, cfg.project = ORG, PROJ
    cfg.repos["Acme.Web"] = str(repo.path)
    cfg.home = tmp_path / ".rca"
    return cfg


def pr_routes(sha, repo_name="Acme.Web"):
    return {
        ("GET", "/workitems/100?"): {**wi(100, "Bug", "Crash", prs=[("repo-1", 55)]),
                                     "fields": {"System.WorkItemType": "Bug", "System.Title": "Crash",
                                                "System.AreaPath": "Acme\\Payroll", "System.IterationPath": "Acme\\PI-12",
                                                "System.State": "Active", "System.Tags": "client-x; urgent",
                                                "Microsoft.VSTS.TCM.ReproSteps": "<p>Open payslip</p>",
                                                "Custom.Environment": "UAT"}},
        ("GET", "/pullrequests/55?"): {
            "pullRequestId": 55, "title": "Fix null total", "status": "completed",
            "repository": {"id": "repo-1", "name": repo_name},
            "sourceRefName": "refs/heads/bugfix/1", "targetRefName": "refs/heads/main",
            "lastMergeSourceCommit": {"commitId": sha["fix_src"]}, "lastMergeTargetCommit": {"commitId": sha["ws"]},
            "lastMergeCommit": {"commitId": sha["fix"]}},
        ("GET", "/pullrequests/55/commits"): {"value": []},
        ("GET", "/pullrequests/55/workitems"): {"value": []},
    }


def test_fetch_from_linked_pr_uses_local_diff_and_caches(git_repo, tmp_path):
    repo, sha = git_repo
    cfg = make_cfg(tmp_path, repo)
    client = AdoClient(ORG, PROJ, FakeTransport(pr_routes(sha)))
    out = fetch(100, cfg, client)
    assert out["source"] == "pr" and out["repo"] == "Acme.Web"
    assert out["base_sha"] == sha["ws"] and out["head_sha"] == sha["fix_src"]
    assert out["bug"]["area_path"] == "Acme\\Payroll"
    assert out["bug"]["repro_steps"] == "Open payslip"
    assert out["bug"]["tags"] == ["client-x", "urgent"]
    assert out["bug"]["extra"] == {"Custom.Environment": "UAT"}
    assert out["files"][0]["path"] == "pay.py"
    assert out["truncated"] is False
    cached = json.loads((cfg.cache_dir / "100.json").read_text(encoding="utf-8"))
    assert cached["files_full"][0]["hunks"][0]["old_start"] >= 1


def test_fetch_no_linked_pr_returns_error(git_repo, tmp_path):
    repo, sha = git_repo
    cfg = make_cfg(tmp_path, repo)
    routes = pr_routes(sha)
    routes[("GET", "/workitems/100?")] = wi(100, "Bug", "Crash")
    out = fetch(100, cfg, AdoClient(ORG, PROJ, FakeTransport(routes)))
    assert out["error"]["code"] == "no_linked_pr"


def test_fetch_repo_not_configured(git_repo, tmp_path):
    repo, sha = git_repo
    cfg = make_cfg(tmp_path, repo)
    out = fetch(100, cfg, AdoClient(ORG, PROJ, FakeTransport(pr_routes(sha, repo_name="Other"))))
    assert out["error"]["code"] == "repo_not_configured"


def test_fetch_branch_mode_diffs_against_default_target(git_repo, tmp_path):
    repo, sha = git_repo
    cfg = make_cfg(tmp_path, repo)
    routes = pr_routes(sha)
    routes[("GET", "/workitems/100?")] = wi(100, "Bug", "Crash")
    out = fetch(100, cfg, AdoClient(ORG, PROJ, FakeTransport(routes)), branch="bugfix/1", repo="Acme.Web")
    assert out["source"] == "branch" and out["pr"] is None
    assert out["base_sha"] == sha["ws"] and out["head_sha"] == sha["fix_src"]
    assert out["files"][0]["path"] == "pay.py"
