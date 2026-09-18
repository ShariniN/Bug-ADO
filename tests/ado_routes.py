"""Fake-transport routes for the v2 endpoints. Keys are (METHOD|TEXT, url substring)."""
from __future__ import annotations

VSSPS = "app.vssps.visualstudio.com"


def org_routes(accounts=("acme", "other"), projects=("Acme", "Beta")):
    return {
        ("GET", "/_apis/profile/profiles/me"): {"id": "me-1"},
        ("GET", "/_apis/accounts?memberId=me-1"): {"value": [{"accountName": a, "accountUri": f"https://dev.azure.com/{a}"} for a in accounts]},
        ("GET", "/_apis/projects?"): {"value": [{"name": p} for p in projects]},
    }


def repo_routes(repo_id="repo-1", name="Acme.Web"):
    return {("GET", "/_apis/git/repositories?"): {"value": [{"id": repo_id, "name": name}]}}


def history_routes(repo_id, path, versions: list[tuple[str, str | None]], refs=(), merge_bases=None):
    """versions: newest first, (sha, text|None). refs: [(name, tip_sha)]. merge_bases: {(sha, other): [sha...]}."""
    r = {}
    r[("GET", f"/repositories/{repo_id}/commits?searchCriteria.itemPath={path}")] = {"value": [{"commitId": s} for s, _ in versions]}
    for sha, text in versions:
        r[("TEXT", f"/repositories/{repo_id}/items?path={path}&versionDescriptor.version={sha}")] = text
    r[("GET", f"/repositories/{repo_id}/refs?filter=heads/")] = {"value": [{"name": f"refs/heads/{n}", "objectId": s} for n, s in refs]}
    for (a, b), out in (merge_bases or {}).items():
        r[("GET", f"/repositories/{repo_id}/commits/{a}/mergebases?otherCommitId={b}")] = {"value": [{"commitId": x} for x in out]}
    return r


def commit_route(repo_id, sha, author="Jo", date="2024-03-01T10:00:00Z", subject="msg", parents=()):
    return {("GET", f"/repositories/{repo_id}/commits/{sha}?"): {
        "commitId": sha, "author": {"name": author, "date": date}, "comment": subject + "\n\nbody", "parents": list(parents)}}


def diff_route(repo_id, base, head, changes):
    """changes: [(path, changeType, old_path|None)] or [(path, changeType, old_path|None, is_folder)]"""
    items = []
    for c in changes:
        p, ct, op = c[:3]
        folder = len(c) > 3 and c[3]
        item = {"path": "/" + p, "gitObjectType": "tree" if folder else "blob"}
        if folder:
            item["isFolder"] = True
        items.append({"item": item, "changeType": ct, **({"sourceServerItem": "/" + op} if op else {})})
    return {("GET", f"/repositories/{repo_id}/diffs/commits?baseVersion={base}"): {"changes": items}}
