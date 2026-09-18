# ado-rca

Fills the Bug RCA template in Azure DevOps from the fix PR. Traces the culprit commit with `git blame`,
finds the PR and work items behind it, proposes Legacy / Feature / Non-Feature, drafts every section, and
publishes to the Bug's fields after you confirm. Runs inside Claude Code as `/rca [bug-id]`.

## Install (teammates)

1. Install `uv` (once): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. In Claude Code, run once:
   ```
   claude plugin marketplace add https://github.com/ShariniN/Bug-ADO.git
   claude plugin install ado-rca@ado-rca
   ```
   then restart Claude Code.
3. Run `/rca-setup` once — it opens a browser to sign in with your Microsoft work account. No PAT or
   password is asked for or stored. It then walks you through picking your org and project and checking
   the RCA field mapping.
4. Run `/rca` on a bug branch (no argument infers the bug from the current branch), or `/rca <bug-id>`.
   If you are not set up yet, `/rca` runs the setup steps inline the first time.

## Team admin (once)

Browser sign-in needs an Entra app registration for the team:

1. Register a new app in Entra ID (App registrations → New registration).
   - Supported account types: your organization's directory.
   - Redirect URI: platform **Public client/native**, `http://localhost`.
2. **Authentication** → under "Advanced settings", enable **Allow public client flows**.
3. **API permissions** → Add a permission → **Azure DevOps** → Delegated permissions → `user_impersonation`.
   Grant admin consent if your tenant requires it.
4. Put the app's `client_id` and the tenant's `tenant_id` under `[auth]` in
   `src/rca_core/defaults/team.toml`, and set `org_url` / `project` there too so teammates don't need to
   pick them. Commit and release.

### PAT fallback

If browser sign-in isn't available (no Entra app yet, or a headless environment), set `mode = "pat"` under
`[auth]` in `~/.rca/config.toml` (or team.toml) and create an Azure DevOps PAT with **Work Items (read &
write)** and **Code (read)** scopes, then set it in the env var named by `pat_env` (default `ADO_PAT`):
`[Environment]::SetEnvironmentVariable("ADO_PAT", "<token>", "User")`, and restart Claude Code.

## How it works

`rca_fetch` → Bug + fix diff (linked PR, PR of the current branch, or the local branch diff, in that
order) → local diff hunks. `rca_trace` → blame pre-fix lines → culprit commits → merging PR →
work items → parent chain → release branches → earliest version. `rca_classify` → proposal with confidence.
Claude drafts the 13 sections; you confirm; `rca_publish` PATCHes the Bug.

Config: team defaults in `src/rca_core/defaults/team.toml`; personal overrides in `~/.rca/config.toml`.
Cache: `~/.rca/cache/<bug>.json`. Credentials (browser token or PAT) are never written to disk.

## Develop

```
python -m pip install -e ".[dev]"
python -m pytest
rca fields            # check field mapping against your project
rca fetch 12345       # JSON output; same operations the MCP tools expose
```

Manual CLI equivalents: `rca fetch|trace|classify|fields|publish|version`.
Opt-in live smoke test against the real org: `RCA_LIVE=1 RCA_LIVE_BUG=<id> python -m pytest tests/test_live_smoke.py`.
Release: bump `version` in `pyproject.toml`, `plugin/.claude-plugin/plugin.json`, and `plugin/.mcp.json` (the `@vX.Y.Z` ref), tag `vX.Y.Z`, push.
