from __future__ import annotations

import os
import re
import subprocess
from importlib import metadata

from rca_core.versions import parse_version

_TAG = re.compile(r"refs/tags/v?(\d+\.\d+\.\d+)$")


def current_version() -> str:
    try:
        return metadata.version("ado-rca")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def newer_tag(repo_url: str, current: str, runner=subprocess.run) -> str | None:
    if not repo_url:
        return None
    try:
        proc = runner(["git", "ls-remote", "--tags", "--refs", repo_url], capture_output=True, text=True, timeout=5,
                      env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"})
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    tags = [m.group(1) for line in proc.stdout.splitlines() if (m := _TAG.search(line.strip()))]
    newer = [t for t in tags if parse_version(t) > parse_version(current)]
    return max(newer, key=parse_version) if newer else None
