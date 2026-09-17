import pytest

from rca_core.ado_client import AdoClient, RequestsTransport
from rca_core.errors import RcaError
from tests.conftest import FakeTransport

ORG, PROJ = "https://dev.azure.com/acme", "Acme"


def wi(id, type_, title, parent=None, prs=()):
    rels = []
    if parent:
        rels.append({"rel": "System.LinkTypes.Hierarchy-Reverse", "url": f"{ORG}/_apis/wit/workItems/{parent}"})
    for repo, pr in prs:
        rels.append({"rel": "ArtifactLink", "url": f"vstfs:///Git/PullRequestId/proj-guid%2F{repo}%2F{pr}",
                     "attributes": {"name": "Pull Request"}})
    return {"id": id, "fields": {"System.WorkItemType": type_, "System.Title": title,
                                 "System.IterationPath": "Acme\\PI-12\\S1", "System.State": "Active"},
            "relations": rels}


def test_linked_pr_ids_and_parent_chain():
    t = FakeTransport({
        ("GET", "/workitems/100?"): wi(100, "Bug", "Crash", parent=200, prs=[("repo-1", 55)]),
        ("GET", "/workitems/200?"): wi(200, "User Story", "Story", parent=300),
        ("GET", "/workitems/300?"): wi(300, "Feature", "Big Feature"),
    })
    c = AdoClient(ORG, PROJ, t)
    bug = c.get_work_item(100)
    assert c.linked_pr_ids(bug) == [("repo-1", 55)]
    chain = c.parent_chain(100)
    assert [(w.id, w.type) for w in chain] == [(200, "User Story"), (300, "Feature")]
    assert chain[1].iteration == "Acme\\PI-12\\S1"


def test_get_pull_request_assembles_info():
    t = FakeTransport({
        ("GET", "/pullrequests/55?"): {
            "pullRequestId": 55, "title": "Fix crash", "status": "completed",
            "repository": {"id": "repo-1", "name": "Acme.Web"},
            "sourceRefName": "refs/heads/bugfix/100", "targetRefName": "refs/heads/main",
            "lastMergeSourceCommit": {"commitId": "s" * 40}, "lastMergeTargetCommit": {"commitId": "t" * 40},
            "lastMergeCommit": {"commitId": "m" * 40},
        },
        ("GET", "/pullrequests/55/commits"): {"value": [
            {"commitId": "s" * 40, "comment": "fix crash\n\nlong body", "author": {"name": "Jo", "date": "2024-05-01T10:00:00Z"}}]},
        ("GET", "/pullrequests/55/workitems"): {"value": [{"id": "100"}]},
        ("GET", "/workitems?ids=100"): {"value": [wi(100, "Bug", "Crash")]},
    })
    pr = AdoClient(ORG, PROJ, t).get_pull_request("repo-1", 55)
    assert pr.repo_name == "Acme.Web" and pr.source_branch == "bugfix/100" and pr.target_branch == "main"
    assert pr.source_sha == "s" * 40 and pr.merge_sha == "m" * 40
    assert pr.commits == [{"sha": "s" * 40, "subject": "fix crash", "author": "Jo", "date": "2024-05-01"}]
    assert [w.id for w in pr.work_items] == [100]


def test_find_pr_ids_for_commit_posts_query():
    t = FakeTransport({("POST", "/pullrequestquery"): {"results": [{"c" * 40: [{"pullRequestId": 9}]}]}})
    c = AdoClient(ORG, PROJ, t)
    assert c.find_pr_ids_for_commit("repo-1", "c" * 40) == [9]
    assert t.calls[0][2] == {"queries": [{"items": ["c" * 40], "type": "commit"}]}


def test_bug_fields_merges_types():
    t = FakeTransport({
        ("GET", "/workitemtypes/Bug/fields"): {"value": [
            {"referenceName": "Custom.BugClassification", "name": "Bug Classification", "allowedValues": ["Legacy Bug"]}]},
        ("GET", "/_apis/wit/fields?"): {"value": [{"referenceName": "Custom.BugClassification", "type": "string"}]},
    })
    fields = AdoClient(ORG, PROJ, t).bug_fields()
    assert fields == [{"referenceName": "Custom.BugClassification", "name": "Bug Classification",
                       "type": "string", "allowedValues": ["Legacy Bug"]}]


def test_patch_work_item_builds_json_patch():
    t = FakeTransport({("PATCH", "/workitems/100?"): {"id": 100, "rev": 7, "_links": {"html": {"href": "http://x"}}}})
    c = AdoClient(ORG, PROJ, t)
    out = c.patch_work_item(100, {"Custom.RootCause": "null ref"})
    assert out == {"id": 100, "rev": 7, "url": "http://x"}
    assert t.calls[0][2] == [{"op": "add", "path": "/fields/Custom.RootCause", "value": "null ref"}]


def test_bug_not_found_maps_to_rca_error():
    def raise_404(_):
        raise RcaError("not_found", "404", "")
    t = FakeTransport({("GET", "/workitems/1?"): raise_404})
    with pytest.raises(RcaError) as e:
        AdoClient(ORG, PROJ, t).get_work_item(1)
    assert e.value.code == "bug_not_found"


def test_requests_transport_auth_header():
    tr = RequestsTransport("pat123")
    assert tr.session.headers["Authorization"].startswith("Basic ")


def test_requests_transport_404_carries_actionable_fix():
    from types import SimpleNamespace
    tr = RequestsTransport("pat123")
    tr.session.request = lambda *a, **k: SimpleNamespace(status_code=404, content=b"", text="")
    with pytest.raises(RcaError) as e:
        tr.request("GET", "https://dev.azure.com/acme/Acme/_apis/git/repositories/r/pullrequests/1?api-version=7.1")
    assert e.value.code == "not_found"
    assert e.value.fix and "config.toml" in e.value.fix
