from __future__ import annotations

import base64
import re
from typing import Any, Callable, Protocol
from urllib.parse import quote

import requests

from rca_core.errors import RcaError
from rca_core.models import PullRequestInfo, WorkItemRef

API = "api-version=7.1"
_PR_LINK = re.compile(r"PullRequestId/[^%]+%2F([^%]+)%2F(\d+)$")
_WI_URL = re.compile(r"/workItems/(\d+)$", re.IGNORECASE)


class Transport(Protocol):
    def request(self, method: str, url: str, json: Any = None, content_type: str = "application/json") -> Any: ...
    def get_text(self, url: str, accept: str = "*/*") -> str | None: ...


class RequestsTransport:
    def __init__(self, pat: str | None = None, token_provider: Callable[[], str] | None = None, timeout: float = 30.0) -> None:
        if not pat and token_provider is None:
            raise ValueError("RequestsTransport needs a PAT or a token provider")
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"
        if pat:
            self.session.headers["Authorization"] = "Basic " + base64.b64encode(f":{pat}".encode()).decode()
        self.token_provider = token_provider
        self.timeout = timeout

    def _send(self, method: str, url: str, json: Any, content_type: str, accept: str | None = None):
        headers = {"Content-Type": content_type}
        if accept:
            headers["Accept"] = accept
        if self.token_provider is not None:
            headers["Authorization"] = f"Bearer {self.token_provider()}"
        resp = self.session.request(method, url, json=json, headers=headers, timeout=self.timeout)
        if resp.status_code in (401, 203):  # 203 = HTML sign-in page
            raise RcaError("auth_failed", "Azure DevOps rejected the credentials.",
                           "Sign in again with /rca-setup (browser mode) or check the PAT's expiry and scopes (pat mode).")
        if resp.status_code == 404:
            raise RcaError("not_found", f"404 for {url}",
                           "Check ado.org_url and ado.project in ~/.rca/config.toml, and that the repository, "
                           "pull request or work item id still exists.")
        if resp.status_code >= 400:
            raise RcaError("publish_rejected" if method == "PATCH" else "ado_error",
                           f"{resp.status_code} from Azure DevOps: {resp.text[:300]}",
                           "Read the message above; usually a field name or value is invalid.")
        return resp

    def request(self, method: str, url: str, json: Any = None, content_type: str = "application/json") -> Any:
        resp = self._send(method, url, json, content_type)
        return resp.json() if resp.content else {}

    def get_text(self, url: str, accept: str = "*/*") -> str | None:
        try:
            return self._send("GET", url, None, "application/json", accept=accept).text
        except RcaError as e:
            if e.code == "not_found":
                return None
            raise


class AdoClient:
    def __init__(self, org_url: str, project: str, transport: Transport) -> None:
        self.org = org_url.rstrip("/")
        self.project = project
        self.t = transport

    # ---- URLs -------------------------------------------------------------
    def _wit(self, path: str) -> str:
        return f"{self.org}/{self.project}/_apis/wit/{path}"

    def _git(self, repo_id: str, path: str) -> str:
        return f"{self.org}/{self.project}/_apis/git/repositories/{repo_id}/{path}"

    def work_item_url(self, id: int) -> str:
        return f"{self.org}/{self.project}/_workitems/edit/{id}"

    def pull_request_url(self, repo_name: str, pr_id: int) -> str:
        return f"{self.org}/{self.project}/_git/{repo_name}/pullrequest/{pr_id}"

    # ---- Work items -------------------------------------------------------
    def get_work_item(self, id: int) -> dict:
        try:
            return self.t.request("GET", self._wit(f"workitems/{id}?$expand=relations&{API}"))
        except RcaError as e:
            if e.code == "not_found":
                raise RcaError("bug_not_found", f"Work item {id} was not found in project {self.project}.",
                               "Check the Bug ID and that ~/.rca/config.toml points at the right project.") from e
            raise

    def get_work_items(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []
        joined = ",".join(str(i) for i in ids)
        return self.t.request("GET", self._wit(f"workitems?ids={joined}&$expand=relations&{API}")).get("value", [])

    @staticmethod
    def to_ref(w: dict) -> WorkItemRef:
        f = w.get("fields", {})
        return WorkItemRef(id=int(w["id"]), type=f.get("System.WorkItemType", ""),
                           title=f.get("System.Title", "")[:80], iteration=f.get("System.IterationPath", ""),
                           state=f.get("System.State", ""))

    @staticmethod
    def linked_pr_ids(w: dict) -> list[tuple[str, int]]:
        out: list[tuple[str, int]] = []
        for rel in w.get("relations", []) or []:
            if rel.get("rel") == "ArtifactLink" and (m := _PR_LINK.search(rel.get("url", ""))):
                out.append((m.group(1), int(m.group(2))))
        return out

    @staticmethod
    def parent_id(w: dict) -> int | None:
        for rel in w.get("relations", []) or []:
            if rel.get("rel") == "System.LinkTypes.Hierarchy-Reverse" and (m := _WI_URL.search(rel.get("url", ""))):
                return int(m.group(1))
        return None

    def parent_chain(self, id: int, max_depth: int = 5) -> list[WorkItemRef]:
        chain: list[WorkItemRef] = []
        current = self.get_work_item(id)
        for _ in range(max_depth):
            pid = self.parent_id(current)
            if pid is None:
                break
            current = self.get_work_item(pid)
            chain.append(self.to_ref(current))
        return chain

    # ---- Pull requests ----------------------------------------------------
    def get_pull_request(self, repo_id: str, pr_id: int) -> PullRequestInfo:
        pr = self.t.request("GET", self._git(repo_id, f"pullrequests/{pr_id}?{API}"))
        commits_raw = self.t.request("GET", self._git(repo_id, f"pullrequests/{pr_id}/commits?{API}")).get("value", [])
        wi_ids = [int(x["id"]) for x in self.t.request("GET", self._git(repo_id, f"pullrequests/{pr_id}/workitems?{API}")).get("value", [])]
        work_items = [self.to_ref(w) for w in self.get_work_items(wi_ids)]
        strip = lambda ref: ref.replace("refs/heads/", "")
        return PullRequestInfo(
            id=int(pr["pullRequestId"]), title=pr.get("title", ""),
            repo_name=pr["repository"]["name"], repo_id=pr["repository"]["id"],
            source_branch=strip(pr.get("sourceRefName", "")), target_branch=strip(pr.get("targetRefName", "")),
            source_sha=pr.get("lastMergeSourceCommit", {}).get("commitId", ""),
            target_sha=pr.get("lastMergeTargetCommit", {}).get("commitId", ""),
            merge_sha=pr.get("lastMergeCommit", {}).get("commitId"),
            status=pr.get("status", ""), work_items=work_items,
            commits=[{"sha": c["commitId"], "subject": c.get("comment", "").splitlines()[0][:120] if c.get("comment") else "",
                      "author": c.get("author", {}).get("name", ""), "date": c.get("author", {}).get("date", "")[:10]}
                     for c in commits_raw],
        )

    def find_pr_ids_for_commit(self, repo_id: str, sha: str) -> list[int]:
        body = {"queries": [{"items": [sha], "type": "commit"}]}
        res = self.t.request("POST", self._git(repo_id, f"pullrequestquery?{API}"), json=body)
        ids: list[int] = []
        for group in res.get("results", []):
            for prs in group.values():
                ids.extend(int(p["pullRequestId"]) for p in prs)
        return ids

    # ---- Fields -----------------------------------------------------------
    def bug_fields(self) -> list[dict]:
        typed = self.t.request("GET", self._wit(f"workitemtypes/Bug/fields?$expand=allowedValues&{API}")).get("value", [])
        all_fields = self.t.request("GET", f"{self.org}/_apis/wit/fields?{API}").get("value", [])
        types = {f["referenceName"]: f.get("type", "") for f in all_fields}
        return [{"referenceName": f["referenceName"], "name": f.get("name", ""),
                 "type": types.get(f["referenceName"], ""), "allowedValues": f.get("allowedValues", [])}
                for f in typed]

    def patch_work_item(self, id: int, fields: dict[str, str]) -> dict:
        ops = [{"op": "add", "path": f"/fields/{ref}", "value": val} for ref, val in fields.items()]
        res = self.t.request("PATCH", self._wit(f"workitems/{id}?{API}"), json=ops, content_type="application/json-patch+json")
        return {"id": res.get("id", id), "rev": res.get("rev"), "url": res.get("_links", {}).get("html", {}).get("href", self.work_item_url(id))}

    # ---- Org discovery ----------------------------------------------------
    VSSPS = "https://app.vssps.visualstudio.com/_apis"

    def profile_me(self) -> dict:
        return self.t.request("GET", f"{self.VSSPS}/profile/profiles/me?{API}")

    def list_accounts(self) -> list[dict]:
        me = self.profile_me()["id"]
        res = self.t.request("GET", f"{self.VSSPS}/accounts?memberId={me}&{API}")
        return sorted(({"name": a["accountName"], "url": a.get("accountUri", f"https://dev.azure.com/{a['accountName']}")}
                       for a in res.get("value", [])), key=lambda a: a["name"].lower())

    def list_projects(self) -> list[str]:
        res = self.t.request("GET", f"{self.org}/_apis/projects?$top=500&{API}")
        return sorted((p["name"] for p in res.get("value", [])), key=str.lower)

    def list_repositories(self) -> list[dict]:
        res = self.t.request("GET", f"{self.org}/{self.project}/_apis/git/repositories?{API}")
        return [{"id": r["id"], "name": r["name"]} for r in res.get("value", [])]

    def iteration_tree(self) -> dict:
        return self.t.request("GET", self._wit(f"classificationnodes/Iterations?$depth=5&{API}"))

    # ---- Git history --------------------------------------------------------
    def get_refs(self, repo_id: str, filter: str = "heads/") -> list[dict]:
        res = self.t.request("GET", self._git(repo_id, f"refs?filter={filter}&{API}"))
        return [{"name": r["name"].removeprefix("refs/heads/"), "sha": r["objectId"]} for r in res.get("value", [])]

    def merge_bases(self, repo_id: str, sha: str, other: str) -> list[str]:
        res = self.t.request("GET", self._git(repo_id, f"commits/{sha}/mergebases?otherCommitId={other}&{API}"))
        return [c["commitId"] for c in res.get("value", [])]

    def get_commit(self, repo_id: str, sha: str) -> dict:
        c = self.t.request("GET", self._git(repo_id, f"commits/{sha}?{API}"))
        comment = c.get("comment", "") or ""
        return {"sha": c["commitId"], "author": c.get("author", {}).get("name", ""),
                "date": c.get("author", {}).get("date", "")[:10],
                "subject": comment.splitlines()[0][:120] if comment else "", "parents": list(c.get("parents", []))}

    def path_history(self, repo_id: str, path: str, sha: str, top: int = 100) -> list[str]:
        url = self._git(repo_id, f"commits?searchCriteria.itemPath={quote(path)}&searchCriteria.itemVersion.version={sha}"
                                 f"&searchCriteria.itemVersion.versionType=commit&searchCriteria.$top={top}&{API}")
        return [c["commitId"] for c in self.t.request("GET", url).get("value", [])]

    def get_item_text(self, repo_id: str, path: str, sha: str) -> str | None:
        url = self._git(repo_id, f"items?path={quote(path)}&versionDescriptor.version={sha}"
                                 f"&versionDescriptor.versionType=commit&includeContent=true&{API}")
        return self.t.get_text(url)

    def changed_paths(self, repo_id: str, base: str, head: str) -> list[dict]:
        url = self._git(repo_id, f"diffs/commits?baseVersion={base}&baseVersionType=commit&targetVersion={head}"
                                 f"&targetVersionType=commit&$top=1000&{API}")
        out: list[dict] = []
        for ch in self.t.request("GET", url).get("changes", []):
            item = ch.get("item", {})
            if item.get("gitObjectType", "blob") != "blob" or item.get("isFolder"):
                continue
            ct = (ch.get("changeType") or "edit").lower()
            change = "delete" if "delete" in ct else "add" if "add" in ct else "modify"
            path = item["path"].lstrip("/")
            old = (ch.get("sourceServerItem") or item["path"]).lstrip("/")
            out.append({"path": path, "old_path": old, "change": change})
        return out

    def find_prs_by_source_branch(self, branch: str) -> list[dict]:
        url = (f"{self.org}/{self.project}/_apis/git/pullrequests?searchCriteria.sourceRefName=refs/heads/{quote(branch, safe='/')}"
               f"&searchCriteria.status=all&{API}")
        prs = self.t.request("GET", url).get("value", [])
        return sorted(({"id": int(p["pullRequestId"]), "repo_id": p["repository"]["id"],
                        "repo_name": p["repository"].get("name", ""), "status": p.get("status", "")} for p in prs),
                      key=lambda p: -p["id"])

    def pr_repo_id(self, pr_id: int) -> str:
        return self.t.request("GET", f"{self.org}/_apis/git/pullrequests/{pr_id}?{API}")["repository"]["id"]
