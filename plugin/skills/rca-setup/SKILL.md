---
name: rca-setup
description: One-time setup for the ado-rca plugin on this machine (org, project, PAT env var, repo paths, field check).
---

# /rca-setup

Create or update `~/.rca/config.toml`. Never ask for or store the PAT value itself; only the env var name.

1. Ask, one at a time, with defaults from the existing file if present:
   - Azure DevOps org URL (e.g. `https://dev.azure.com/peopleshr`)
   - Project name
   - Name of the environment variable holding the PAT (default `ADO_PAT`). Tell the user how to set it persistently:
     `[Environment]::SetEnvironmentVariable("ADO_PAT", "<token>", "User")` in PowerShell, then restart Claude Code.
   - For each repo they fix bugs in: the repo name exactly as in Azure Repos, and its local clone path.
2. Write `~/.rca/config.toml` (create the folder if needed):

   ```toml
   [ado]
   org_url = "<org>"
   project = "<project>"
   pat_env = "<env var>"

   [repos]
   "<RepoName>" = "<C:/path/to/clone>"
   ```

   Only include `[git]` or `[fields]` tables if the user asks to override team defaults.
3. Call `rca_fields()`.
   - On `error` with code `no_pat` or `auth_failed`: show `fix`, and stop; tell them to rerun `/rca-setup` after fixing.
   - If `ok` is false: for each issue show `section`, `configured`, `suggestion`. Ask whether to accept each suggestion
     or type a reference name. Write accepted mappings under `[fields]` in `~/.rca/config.toml` and call `rca_fields()` again.
   - If a suggestion is accepted that differs from the team default, tell the user to raise a PR updating
     `src/rca_core/defaults/team.toml` so the whole team gets it.
4. Finish with: `Setup complete. Run /rca <bug-id> on a bug with a linked PR.`
