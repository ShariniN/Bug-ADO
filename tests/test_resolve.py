import pytest

from rca_core.ado_client import AdoClient
from rca_core.errors import RcaError
from rca_core.resolve import resolve_bug
from tests.conftest import FakeTransport
from tests.test_ado_client import ORG, PROJ, wi


def client(routes=None):
    return AdoClient(ORG, PROJ, FakeTransport(routes or {}))


def test_numeric_and_url():
    assert resolve_bug("12345", client(), None)["bug_id"] == 12345
    assert resolve_bug(7, client(), None)["how"] == "argument"
    out = resolve_bug("https://dev.azure.com/acme/Acme/_workitems/edit/999/", client(), None)
    assert out["bug_id"] == 999 and out["how"] == "url"


def test_garbage_and_no_repo():
    with pytest.raises(RcaError) as e:
        resolve_bug("abc", client(), None)
    assert e.value.code == "bug_not_resolved"
    with pytest.raises(RcaError) as e2:
        resolve_bug("", client(), None)
    assert e2.value.code == "bug_not_resolved"


def test_branch_pr_links_bug(git_repo):
    repo, sha = git_repo
    repo.run("checkout", "-q", "bugfix/1")
    routes = {
        ("GET", "/_apis/git/pullrequests?searchCriteria.sourceRefName=refs/heads/bugfix/1"): {"value": [
            {"pullRequestId": 5, "status": "active", "repository": {"id": "repo-1", "name": "Acme.Web"}}]},
        ("GET", "/pullrequests/5?"): {"pullRequestId": 5, "title": "t", "status": "active", "repository": {"id": "repo-1", "name": "Acme.Web"},
                                      "sourceRefName": "refs/heads/bugfix/1", "targetRefName": "refs/heads/main"},
        ("GET", "/pullrequests/5/commits"): {"value": []},
        ("GET", "/pullrequests/5/workitems"): {"value": [{"id": "300"}, {"id": "100"}]},
        ("GET", "/workitems?ids=300,100"): {"value": [wi(300, "Task", "t"), wi(100, "Bug", "Crash")]},
    }
    out = resolve_bug("", client(routes), repo.path)
    assert out == {"bug_id": 100, "how": "PR 5 for branch bugfix/1", "pr_id": 5, "repo_id": "repo-1"}


def test_branch_name_id(git_repo):
    repo, sha = git_repo
    repo.run("checkout", "-q", "-b", "bugfix/12345-crash")
    routes = {("GET", "/_apis/git/pullrequests?searchCriteria.sourceRefName="): {"value": []},
              ("GET", "/workitems/12345?"): wi(12345, "Bug", "Crash")}
    out = resolve_bug(None, client(routes), repo.path)
    assert out["bug_id"] == 12345 and out["pr_id"] is None and "branch name" in out["how"]


def test_branch_name_id_from_subdirectory(git_repo):
    repo, sha = git_repo
    repo.run("checkout", "-q", "-b", "bugfix/12345-crash")
    sub = repo.path / "src" / "deep"
    sub.mkdir(parents=True)
    routes = {("GET", "/_apis/git/pullrequests?searchCriteria.sourceRefName="): {"value": []},
              ("GET", "/workitems/12345?"): wi(12345, "Bug", "Crash")}
    assert resolve_bug("", client(routes), sub)["bug_id"] == 12345


def test_branch_scan_accepts_custom_bug_type(git_repo):
    repo, sha = git_repo
    repo.run("checkout", "-q", "-b", "bugfix/12345-crash")
    routes = {("GET", "/_apis/git/pullrequests?searchCriteria.sourceRefName="): {"value": []},
              ("GET", "/workitems/12345?"): wi(12345, "Issue", "Crash")}
    out = resolve_bug(None, client(routes), repo.path, bug_type="Issue")
    assert out["bug_id"] == 12345


def test_only_real_work_item_urls_match():
    with pytest.raises(RcaError):
        resolve_bug("https://example.com/edit/123", client(), None)


def test_auth_errors_propagate_from_branch_scan(git_repo):
    repo, sha = git_repo
    repo.run("checkout", "-q", "-b", "bugfix/12345-crash")

    def boom(_):
        raise RcaError("auth_failed", "rejected", "sign in")

    routes = {("GET", "/_apis/git/pullrequests?searchCriteria.sourceRefName="): {"value": []},
              ("GET", "/workitems/12345?"): boom}
    with pytest.raises(RcaError) as e:
        resolve_bug("", client(routes), repo.path)
    assert e.value.code == "auth_failed"
