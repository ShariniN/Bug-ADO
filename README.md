# ado-rca

Fills the Bug RCA template in Azure DevOps from the fix PR. Traces the culprit commit with `git blame`,
finds the PR and work items behind it, proposes Legacy / Feature / Non-Feature, drafts every section, and
publishes to the Bug's fields after you confirm. Runs inside Claude Code as `/rca <bug-id>`.

## Install (teammates)

1. Install `uv` (once): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. Create an Azure DevOps PAT with **Work Items (read & write)** and **Code (read)** scopes and set it:
   `[Environment]::SetEnvironmentVariable("ADO_PAT", "<token>", "User")`
3. In Claude Code, run once:
   ```
   claude plugin marketplace add https://github.com/ShariniN/Bug-ADO.git
   claude plugin install ado-rca@ado-rca
   ```
   then restart Claude Code.
4. Run `/rca-setup` once. Then `/rca <bug-id>`.

## How it works

`rca_fetch` → Bug + linked PR + local diff hunks. `rca_trace` → blame pre-fix lines → culprit commits → merging PR →
work items → parent chain → release branches → earliest version. `rca_classify` → proposal with confidence.
Claude drafts the 13 sections; you confirm; `rca_publish` PATCHes the Bug.

Config: team defaults in `src/rca_core/defaults/team.toml`; personal overrides in `~/.rca/config.toml`.
Cache: `~/.rca/cache/<bug>.json`. The PAT is only ever read from the environment.

## Develop

```
python -m pip install -e ".[dev]"
python -m pytest
rca fields            # check field mapping against your project
rca fetch 12345       # JSON output; same operations the MCP tools expose
```

Manual CLI equivalents: `rca fetch|trace|classify|fields|publish|version`.
Release: bump `version` in `pyproject.toml`, `plugin/.claude-plugin/plugin.json`, and `plugin/.mcp.json` (the `@vX.Y.Z` ref), tag `vX.Y.Z`, push.
