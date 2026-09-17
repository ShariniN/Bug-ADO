from __future__ import annotations

import re
from typing import Callable

from rca_core.ado_client import AdoClient
from rca_core.cache import read_cache, write_cache
from rca_core.config import Config
from rca_core.errors import RcaError, guarded
from rca_core.git_forensics import GitRepo, blame_hunks, has_removed_lines
from rca_core.models import Culprit, Hunk, TraceResult, to_dict
from rca_core.versions import earliest_version

MAX_CULPRITS = 3
TRACE_CAP_BYTES = 4000


def _cap(evidence: list[str], limit: int) -> list[str]:
    out, used = [], 0
    for e in evidence:
        if used + len(e) > limit:
            out.append("... (evidence truncated)")
            break
        out.append(e)
        used += len(e)
    return out


@guarded
def trace(bug_id: int, cfg: Config, client: AdoClient, repo_factory: Callable[..., GitRepo] = GitRepo) -> dict:
    cached = read_cache(cfg, bug_id)
    if not cached.get("files_full"):
        raise RcaError("fetch_first", f"No fetched diff cached for bug {bug_id}.", "Run rca_fetch first.")

    repo_name, base_sha = cached["repo"], cached["base_sha"]
    g = repo_factory(cfg.repo_path(repo_name))
    hunks = [Hunk(**h) for f in cached["files_full"] for h in f["hunks"]]
    counts = blame_hunks(g, base_sha, hunks)
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:MAX_CULPRITS]

    evidence = [f"Blamed removed lines across {len(hunks)} hunk(s) at base {base_sha[:8]}; "
                f"{len(counts)} distinct prior commit(s) touched them."]
    notes: list[str] = []
    if not ranked:
        notes.append("No removed lines could be attributed; fix may be pure addition or files are new.")
    if hunks and not has_removed_lines(hunks):
        notes.append("Fix only added lines; culprits are blamed from the 3 lines around each insertion (low confidence).")

    # ADO accepts the repository name in place of its GUID, so branch mode (no cached PR) still works.
    pr_repo_id = (cached.get("pr") or {}).get("repo_id") or repo_name
    target_ref = f"origin/{cfg.default_target_branch}" if g.has_ref(f"origin/{cfg.default_target_branch}") else cfg.default_target_branch
    culprits: list[Culprit] = []

    for sha, lines in ranked:
        info = g.commit_info(sha)
        c = Culprit(sha=sha, author=info["author"], date=info["date"], subject=info["subject"], lines=lines)
        evidence.append(f"Culprit {sha[:8]} ({c.date}, {c.author}) '{c.subject}' authored {lines} of the removed line(s).")

        pr_ids = client.find_pr_ids_for_commit(pr_repo_id, sha) if pr_repo_id else []
        pr_id = pr_ids[0] if pr_ids else g.merged_pr_id_from_history(sha, target_ref)
        if pr_id and pr_repo_id:
            pr = client.get_pull_request(pr_repo_id, pr_id)
            c.pr_id, c.pr_title, c.work_items = pr.id, pr.title, pr.work_items
            evidence.append(f"{sha[:8]} was merged by PR {pr.id} '{pr.title}' ({pr.source_branch} -> {pr.target_branch}).")
            for w in pr.work_items:
                chain = client.parent_chain(w.id)
                if chain and not c.parent_chain:
                    c.parent_chain = chain
                path = " -> ".join(f"{x.type} {x.id}" for x in [w, *chain])
                evidence.append(f"PR {pr.id} links {path}" + (f" (iteration '{chain[-1].iteration}')" if chain else "") + ".")
            if not pr.work_items:
                notes.append(f"PR {pr.id} has no linked work items; feature attribution unavailable.")
        else:
            notes.append(f"No merging PR found for {sha[:8]} (direct commit or history rewritten).")

        c.release_branches = [b for b in g.branches_containing(sha) if re.search(cfg.release_branch_pattern, b)]
        c.earliest_version = earliest_version(c.release_branches, cfg.release_branch_pattern)
        if c.earliest_version:
            evidence.append(f"{sha[:8]} is contained in {', '.join(c.release_branches)}; earliest version {c.earliest_version}.")
        else:
            evidence.append(f"{sha[:8]} is not on any release branch (unreleased or only on {target_ref}).")
            notes.append(f"{sha[:8]} has no release branch; version-based classification is low confidence.")
        if lines <= 1:
            notes.append(f"{sha[:8]} is attributed by a single line; confirm manually.")
        culprits.append(c)

    result = TraceResult(bug_id=bug_id, repo=repo_name, culprits=culprits,
                         evidence=_cap(evidence, TRACE_CAP_BYTES), confidence_notes=notes)
    data = to_dict(result)
    path = write_cache(cfg, bug_id, {"trace": data})
    return {**data, "cache_path": str(path)}
