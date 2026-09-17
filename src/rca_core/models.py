from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


@dataclass
class WorkItemRef:
    id: int
    type: str
    title: str
    iteration: str = ""
    state: str = ""


@dataclass
class Hunk:
    old_path: str
    new_path: str
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    text: str  # hunk body lines joined with "\n", each prefixed by ' ', '-', or '+'


@dataclass
class FileChange:
    path: str          # new path ("" for deletions -> use old_path)
    old_path: str
    change: str        # "add" | "modify" | "delete"
    hunks: list[Hunk] = field(default_factory=list)


@dataclass
class PullRequestInfo:
    id: int
    title: str
    repo_name: str
    repo_id: str
    source_branch: str
    target_branch: str
    source_sha: str
    target_sha: str
    merge_sha: str | None
    status: str
    work_items: list[WorkItemRef] = field(default_factory=list)
    commits: list[dict[str, str]] = field(default_factory=list)  # {sha, subject, author, date}


@dataclass
class BugInfo:
    id: int
    title: str
    state: str
    area_path: str
    iteration_path: str
    repro_steps: str
    description: str
    tags: list[str] = field(default_factory=list)
    extra: dict[str, str] = field(default_factory=dict)  # environment/client style fields
    pr_ids: list[tuple[str, int]] = field(default_factory=list)  # (repo_id, pr_id)


@dataclass
class Culprit:
    sha: str
    author: str
    date: str
    subject: str
    lines: int
    pr_id: int | None = None
    pr_title: str = ""
    work_items: list[WorkItemRef] = field(default_factory=list)
    parent_chain: list[WorkItemRef] = field(default_factory=list)
    release_branches: list[str] = field(default_factory=list)
    earliest_version: str | None = None


@dataclass
class TraceResult:
    bug_id: int
    repo: str
    culprits: list[Culprit]
    evidence: list[str]
    confidence_notes: list[str] = field(default_factory=list)


@dataclass
class Proposal:
    classification: str
    confidence: str          # "high" | "medium" | "low"
    reason: str
    needs_confirmation: bool = False


def to_dict(obj: Any) -> Any:
    """Convert dataclasses (possibly nested in lists/dicts) to plain JSON-able values."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, list):
        return [to_dict(o) for o in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj
