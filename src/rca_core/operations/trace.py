from __future__ import annotations

from typing import Callable

from rca_core.ado_client import AdoClient
from rca_core.ado_history import AdoHistory
from rca_core.cache import read_cache, write_cache
from rca_core.config import Config
from rca_core.errors import RcaError, guarded
from rca_core.git_forensics import blame_hunks, has_removed_lines
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
def trace(bug_id: int, cfg: Config, client: AdoClient, history_factory: Callable[..., AdoHistory] = AdoHistory) -> dict:
    cached = read_cache(cfg, bug_id)
    if not cached.get("files_full"):
        raise RcaError("fetch_first", f"No fetched diff cached for bug {bug_id}.", "Run rca_fetch first.")
    repo_id, base_sha, repo_name = cached.get("repo_id"), cached["base_sha"], cached.get("repo", "")
    if not repo_id:
        raise RcaError("history_unavailable", f"The fix for bug {bug_id} came from a local branch whose repo is not in project {cfg.project}.",
                       "Push the branch and open a PR, or run /rca from a clone whose origin is an Azure Repos repository of this project.")
    hist = history_factory(client, repo_id)
    hunks = [Hunk(**h) for f in cached["files_full"] for h in f["hunks"]]
    counts = blame_hunks(hist, base_sha, hunks)
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:MAX_CULPRITS]

    evidence = [f"Blamed removed lines across {len(hunks)} hunk(s) at base {base_sha[:8]} using Azure DevOps file history; "
                f"{len(counts)} distinct prior commit(s) touched them."]
    notes: list[str] = []
    if not ranked:
        notes.append("No removed lines could be attributed; fix may be pure addition or files are new.")
    if hunks and not has_removed_lines(hunks):
        notes.append("Fix only added lines; culprits are blamed from the 3 lines around each insertion (low confidence).")
    if hist.history_truncated:
        notes.append(f"A culprit fell on the oldest of the {hist.history_top} history entries fetched; the true origin may be older.")

    culprits: list[Culprit] = []
    for sha, lines in ranked:
        info = hist.commit_info(sha)
        c = Culprit(sha=sha, author=info["author"], date=info["date"], subject=info["subject"], lines=lines)
        evidence.append(f"Culprit {sha[:8]} ({c.date}, {c.author}) '{c.subject}' authored {lines} of the removed line(s).")
        pr_ids = client.find_pr_ids_for_commit(repo_id, sha)
        if pr_ids:
            pr = client.get_pull_request(repo_id, min(pr_ids))
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
        c.release_branches = hist.branches_containing(sha, cfg.release_branch_pattern)
        c.earliest_version = earliest_version(c.release_branches, cfg.release_branch_pattern)
        if c.earliest_version:
            evidence.append(f"{sha[:8]} is contained in {', '.join(c.release_branches)}; earliest version {c.earliest_version}.")
        else:
            evidence.append(f"{sha[:8]} is not on any release branch (unreleased).")
            notes.append(f"{sha[:8]} has no release branch; version-based classification is low confidence.")
        if lines <= 1:
            notes.append(f"{sha[:8]} is attributed by a single line; confirm manually.")
        culprits.append(c)

    result = TraceResult(bug_id=bug_id, repo=repo_name, culprits=culprits, evidence=_cap(evidence, TRACE_CAP_BYTES), confidence_notes=notes)
    data = to_dict(result)
    return {**data, "cache_path": str(write_cache(cfg, bug_id, {"trace": data}))}
