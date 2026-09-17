from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rca_core.ado_client import AdoClient, RequestsTransport
from rca_core.config import DEFAULT_USER_PATH, Config, load_config
from rca_core.errors import RcaError
from rca_core.operations.classify import classify_op
from rca_core.operations.fetch import fetch
from rca_core.operations.fields import fields_op
from rca_core.operations.publish import publish
from rca_core.operations.trace import trace
from rca_core.update_check import current_version, newer_tag

USER_CONFIG: Path = DEFAULT_USER_PATH


def build_client(cfg: Config) -> AdoClient:
    return AdoClient(cfg.org_url, cfg.project, RequestsTransport(cfg.pat()))


def run(argv: list[str]) -> dict:
    p = argparse.ArgumentParser(prog="rca", description="Azure DevOps bug RCA assistant")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("bug", type=int); f.add_argument("--pr", type=int)
    f.add_argument("--branch"); f.add_argument("--repo")
    sub.add_parser("trace").add_argument("bug", type=int)
    sub.add_parser("classify").add_argument("bug", type=int)
    sub.add_parser("fields")
    pb = sub.add_parser("publish"); pb.add_argument("bug", type=int)
    pb.add_argument("--sections", required=True, help="JSON file {section_key: value}")
    pb.add_argument("--live", action="store_true", help="actually PATCH the work item (default: dry run)")
    sub.add_parser("version")
    a = p.parse_args(argv)

    if a.cmd == "version":
        cfg = load_config(user_path=USER_CONFIG)
        return {"version": current_version(), "newer": newer_tag(cfg.repo_url, current_version())}

    cfg = load_config(user_path=USER_CONFIG)
    try:
        client = build_client(cfg)
    except RcaError as e:
        return e.to_dict()

    if a.cmd == "fetch":
        out = fetch(a.bug, cfg, client, pr_id=a.pr, branch=a.branch, repo=a.repo)
        if "error" not in out:
            out["update_available"] = newer_tag(cfg.repo_url, current_version())
        return out
    if a.cmd == "trace":
        return trace(a.bug, cfg, client)
    if a.cmd == "classify":
        return classify_op(a.bug, cfg)
    if a.cmd == "fields":
        return fields_op(cfg, client)
    try:
        sections = json.loads(Path(a.sections).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return RcaError("invalid_sections", f"Could not read sections file {a.sections}: {e}",
                        "Pass --sections <path> to a readable JSON file shaped {section_key: text}.").to_dict()
    if not isinstance(sections, dict):
        return RcaError("invalid_sections", "Sections file must contain a JSON object.",
                        "Shape it as {section_key: text}.").to_dict()
    return publish(a.bug, sections, cfg, client, dry_run=not a.live)


def main(argv: list[str] | None = None) -> int:
    result = run(sys.argv[1:] if argv is None else argv)
    print(json.dumps(result, indent=1))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
