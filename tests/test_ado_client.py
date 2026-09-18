from types import SimpleNamespace

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
    tr = RequestsTransport(pat="pat123")
    assert tr.session.headers["Authorization"].startswith("Basic ")


def test_requests_transport_404_carries_actionable_fix():
    from types import SimpleNamespace
    tr = RequestsTransport(pat="pat123")
    tr.session.request = lambda *a, **k: SimpleNamespace(status_code=404, headers={}, content=b"", text="")
    with pytest.raises(RcaError) as e:
        tr.request("GET", "https://dev.azure.com/acme/Acme/_apis/git/repositories/r/pullrequests/1?api-version=7.1")
    assert e.value.code == "not_found"
    assert e.value.fix and "config.toml" in e.value.fix


def _resp(status_code, headers=None, content=b"", text="", json_body=None):
    return SimpleNamespace(status_code=status_code, headers=headers or {}, content=content, text=text,
                            json=lambda: json_body if json_body is not None else {})


def test_retry_after_header_sleeps_capped():
    sleeps = []
    tr = RequestsTransport(pat="p", sleep=sleeps.append)
    tr.session.request = lambda *a, **k: _resp(200, headers={"Retry-After": "120"}, content=b"x", json_body={"ok": True})
    assert tr.request("GET", "https://x") == {"ok": True}
    assert sleeps == [30.0]


def test_429_retries_once():
    sleeps = []
    queue = [_resp(429, headers={"Retry-After": "1"}), _resp(200, headers={}, content=b"x", json_body={"ok": True})]
    tr = RequestsTransport(pat="p", sleep=sleeps.append)
    tr.session.request = lambda *a, **k: queue.pop(0)
    assert tr.request("GET", "https://x") == {"ok": True}
    assert sleeps == [1.0]


def test_429_without_hint_sleeps_floor_then_retries():
    sleeps = []
    queue = [_resp(429), _resp(200, headers={}, content=b"x", json_body={"ok": True})]
    tr = RequestsTransport(pat="p", sleep=sleeps.append)
    tr.session.request = lambda *a, **k: queue.pop(0)
    assert tr.request("GET", "https://x") == {"ok": True}
    assert sleeps == [2.0]


def test_429_twice_raises_throttled():
    sleeps = []
    tr = RequestsTransport(pat="p", sleep=sleeps.append)
    tr.session.request = lambda *a, **k: _resp(429)
    with pytest.raises(RcaError) as e:
        tr.request("GET", "https://x")
    assert e.value.code == "throttled"


def test_401_bearer_is_not_signed_in_and_invalidates():
    calls = []
    tr = RequestsTransport(token_provider=lambda: "tok", on_unauthorized=lambda: calls.append(1))
    tr.session.request = lambda *a, **k: _resp(401)
    with pytest.raises(RcaError) as e:
        tr.request("GET", "https://x/workitems/5?")
    assert calls == [1]
    assert e.value.code == "not_signed_in"
    assert e.value.debug is not None
    assert "http" not in e.value.message.lower()


def test_401_refreshes_once_then_succeeds_without_invalidating():
    calls = []
    token = ["old"]
    queue = [_resp(401), _resp(200, headers={}, content=b"x", json_body={"ok": True})]
    seen_headers = []

    def fake(method, url, json=None, headers=None, timeout=None):
        seen_headers.append(headers)
        return queue.pop(0)

    def refresh():
        token[0] = "new"
        return "new"

    tr = RequestsTransport(token_provider=lambda: token[0], on_unauthorized=lambda: calls.append(1),
                            refresh_token=refresh)
    tr.session.request = fake
    assert tr.request("GET", "https://x") == {"ok": True}
    assert calls == []
    assert seen_headers[1]["Authorization"] == "Bearer new"


def test_401_twice_still_invalidates_once_despite_refresh():
    calls = []
    tr = RequestsTransport(token_provider=lambda: "tok", on_unauthorized=lambda: calls.append(1),
                            refresh_token=lambda: "still-bad")
    tr.session.request = lambda *a, **k: _resp(401)
    with pytest.raises(RcaError) as e:
        tr.request("GET", "https://x")
    assert e.value.code == "not_signed_in"
    assert calls == [1]


def test_401_pat_is_auth_failed():
    tr = RequestsTransport(pat="p")
    tr.session.request = lambda *a, **k: _resp(401)
    with pytest.raises(RcaError) as e:
        tr.request("GET", "https://x")
    assert e.value.code == "auth_failed"


def test_404_message_names_kind():
    tr = RequestsTransport(pat="p")
    tr.session.request = lambda *a, **k: _resp(404)
    with pytest.raises(RcaError) as e:
        tr.request("GET", "https://x/workitems/5?")
    assert "work item" in e.value.message
    assert "http" not in e.value.message.lower()
    assert "https://x/workitems/5?" in e.value.debug


def test_get_work_items_chunks_at_200():
    routes = {("GET", "/workitems?ids="): (lambda body: {"value": []})}
    t = FakeTransport(routes)
    AdoClient(ORG, PROJ, t).get_work_items(list(range(1, 451)))
    calls = [c for c in t.calls if c[0] == "GET" and "/workitems?ids=" in c[1]]
    assert len(calls) == 3
    assert [len(c[1].split("ids=")[1].split("&")[0].split(",")) for c in calls] == [200, 200, 50]


from tests.ado_routes import commit_route, diff_route, history_routes, org_routes, repo_routes


def test_org_discovery():
    c = AdoClient("https://dev.azure.com/acme", "Acme", FakeTransport({**org_routes(), **repo_routes()}))
    assert [a["name"] for a in c.list_accounts()] == ["acme", "other"]
    assert c.list_projects() == ["Acme", "Beta"]
    assert c.list_repositories() == [{"id": "repo-1", "name": "Acme.Web"}]


def test_history_endpoints():
    t = FakeTransport({**history_routes("repo-1", "src/pay.py", [("c3", "a\nb\n"), ("c2", "a\n"), ("c1", None)],
                                        refs=[("release/9.5", "r1"), ("main", "m")], merge_bases={("c2", "r1"): ["c1"]}),
                       **commit_route("repo-1", "c2", parents=["c1"]),
                       **diff_route("repo-1", "c1", "c3", [("src/pay.py", "edit", None), ("new.txt", "add", None), ("old.txt", "delete", None), ("b.txt", "rename", "a.txt"), ("src", "add", None, True)])})
    c = AdoClient("https://dev.azure.com/acme", "Acme", t)
    assert c.path_history("repo-1", "src/pay.py", "c3") == ["c3", "c2", "c1"]
    assert c.get_item_text("repo-1", "src/pay.py", "c2") == "a\n"
    assert c.get_item_text("repo-1", "src/pay.py", "c1") is None
    assert c.get_refs("repo-1") == [{"name": "release/9.5", "sha": "r1"}, {"name": "main", "sha": "m"}]
    assert c.merge_bases("repo-1", "c2", "r1") == ["c1"]
    info = c.get_commit("repo-1", "c2")
    assert info == {"sha": "c2", "author": "Jo", "date": "2024-03-01", "subject": "msg", "parents": ["c1"]}
    assert c.changed_paths("repo-1", "c1", "c3") == [
        {"path": "src/pay.py", "old_path": "src/pay.py", "change": "modify"},
        {"path": "new.txt", "old_path": "new.txt", "change": "add"},
        {"path": "old.txt", "old_path": "old.txt", "change": "delete"},
        {"path": "b.txt", "old_path": "a.txt", "change": "modify"}]


def test_get_text_strips_bom_and_unwraps_json_item():
    from types import SimpleNamespace

    tr = RequestsTransport(pat="p")
    tr.session.request = lambda *a, **k: SimpleNamespace(status_code=200, headers={}, content=b"x", text="﻿hello", encoding=None)
    assert tr.get_text("https://x/items") == "hello"

    tr.session.request = lambda *a, **k: SimpleNamespace(
        status_code=200, headers={}, content=b"x", text='{"objectId":"x","content":"body"}', encoding=None)
    assert tr.get_text("https://x/items") == "body"


def test_prs_by_branch_and_pr_repo_id():
    t = FakeTransport({
        ("GET", "/_apis/git/pullrequests?searchCriteria.sourceRefName=refs/heads/bugfix/1"): {"value": [
            {"pullRequestId": 5, "status": "active", "repository": {"id": "repo-1", "name": "Acme.Web"}},
            {"pullRequestId": 9, "status": "completed", "repository": {"id": "repo-1", "name": "Acme.Web"}}]},
        ("GET", "/_apis/git/pullrequests/9?"): {"pullRequestId": 9, "repository": {"id": "repo-1"}},
        ("GET", "sourceRefName=refs/heads/bug%20fix/1"): {"value": []},
    })
    c = AdoClient("https://dev.azure.com/acme", "Acme", t)
    assert [p["id"] for p in c.find_prs_by_source_branch("bugfix/1")] == [9, 5]
    assert c.pr_repo_id(9) == "repo-1"
    assert c.find_prs_by_source_branch("bug fix/1") == []
