# ADO RCA Assistant v2 — Seamless UX

Date: 2026-09-18
Status: Approved (user), supersedes v1 spec sections noted below
Base: v1 spec `2026-09-17-ado-rca-design.md`, branch `feature/ado-rca` at tag v0.1.0

## 1. Goals

1. No PAT: sign in through the browser with the work account (Microsoft Entra ID, own app registration).
2. No config editing: setup picks org and project from lists, auto-maps fields, detects the current PI.
3. No local clone requirement: all history questions (blame, branch containment, commit metadata, diffs
   between commits) are answered from the Azure DevOps REST API. The fix is taken from the linked PR first;
   only when there is no PR does the tool diff the local branch the user is currently on (the repo Claude
   Code is running in).
4. `/rca` with no arguments infers the bug from the current branch; a pasted work-item URL also works.
5. First `/rca` on an unconfigured machine runs setup inline and continues.

## 2. Authentication

- New module `rca_core/auth.py` using `msal` + `msal-extensions`.
- Config `[auth]`: `mode = "browser" | "pat"` (default browser), `client_id`, `tenant_id` (team defaults;
  filled by the team's app registration: public client, redirect `http://localhost`, permission
  "Azure DevOps → user_impersonation"). Scope: `499b84ac-1321-427f-aa17-267ca6975798/.default`.
- Token cache: `~/.rca/msal_cache.bin`, encrypted with DPAPI on Windows (msal-extensions), file-based
  fallback elsewhere. `acquire_token_silent` first; then `acquire_token_interactive` (opens browser);
  if that raises (no browser), device-code flow in two steps: `rca_login()` returns
  `{device_code_message, verification_uri, user_code}` and stores the flow in `~/.rca/device_flow.json`;
  `rca_login(complete=True)` finishes it.
- `RequestsTransport` accepts either `pat=` (Basic) or `token_provider=` (callable → Bearer). All
  existing client code is unchanged.
- Error code `not_signed_in` (fix: run `/rca-setup` or `rca_login`). PAT mode unchanged for fallback.
- Nothing is ever printed to stdout by auth code (stdout is the MCP channel); messages go in tool results.

## 3. History from Azure DevOps (replaces v1 §4 local-git forensics for trace)

`rca_core/ado_history.py` — class `AdoHistory(client, repo_id)` with the same method names trace uses:

| Method | REST calls |
|---|---|
| `changed_paths(base, head)` | `GET diffs/commits?baseVersion=&baseVersionType=commit&targetVersion=&targetVersionType=commit` → `changes[]` (skip folders, binary by extension list) |
| `file_lines(sha, path)` | `GET items?path=&versionDescriptor.version=&versionDescriptor.versionType=commit&includeContent=true` (JSON `content`; raw text fallback); cached per (sha,path); missing → `None` |
| `diff(base, head)` | unified diff text built with `difflib.unified_diff` over `file_lines` of every changed path (`---/+++` a/ b/ headers so `parse_unified_diff` works unchanged; adds/deletes use `/dev/null`) |
| `path_history(path, sha, top=100)` | `GET commits?searchCriteria.itemPath=&searchCriteria.itemVersion.version=&…versionType=commit&searchCriteria.$top=` → newest first |
| `blame_lines(sha, path, line_numbers)` | **emulated blame**: for each requested line at `sha`, key = line with all whitespace removed (this is `git blame -w`). Over `path_history` (index 0 = `sha` state), binary-search the oldest commit whose content still contains the key; that commit is the culprit. Returns `{line_no: sha}`; lines whose key exists at the oldest fetched commit map to that commit and a `history_truncated` flag is set. |
| `commit_info(sha)` | `GET commits/{sha}` → `{sha, author, date(YYYY-MM-DD), subject}` |
| `branches_containing(sha, pattern)` | `GET refs?filter=heads/` filtered by regex `pattern`; for each tip: `GET commits/{sha}/mergebases?otherCommitId={tip}`; contained iff a merge base equals `sha` |
| `merge_base(a, b)` | mergebases API |

Trace uses `AdoHistory` exclusively (no `merged_pr_id_from_history` fallback; `pullrequestquery` is authoritative). `blame_hunks` moves to a generic function taking any object with `blame_lines`; the pure-addition and whitespace rules from v1 remain. Request budget per trace: ≤ 3 paths × (1 history + ≤ ~8 contents) + refs + ≤ 20 merge-base calls.

## 4. Fetch (replaces v1 §3.1 fetch behaviour)

Order: (1) explicit `pr_id`; (2) PR linked to the Bug (latest); (3) PR whose source branch is the current
local branch (`GET pullrequests?searchCriteria.sourceRefName=refs/heads/<branch>&status=all`); (4) local
branch diff via `GitRepo(cwd)` against `origin/<default>` (fallback `<default>`), only if cwd is a git repo.
For PR sources: `base = merge_base(target_sha, source_sha)` (ADO), `head = source_sha` if it exists else
`merge_sha` with `base = merge_sha^1` (`GET commits/{merge}` → `parents[0]`), diff from `AdoHistory`.
Config `[repos]` is removed; `default_target_branch` stays. Cache keys unchanged; add `repo_id`.

**Bug resolution** (`rca_core/resolve.py`): `resolve_bug(arg, client, git_cwd) -> int`:
- int or digit string → itself; work-item URL (`…/_workitems/edit/12345` or `…/edit/12345`) → id;
- empty: current branch → PR by source branch → its linked work items of type Bug (first); else a
  `\b(\d{3,7})\b` in the branch name whose work item type is Bug; else error `bug_not_resolved` with fix.

## 5. Current PI detection

`rca_core/iterations.py`: `current_pi(tree, today, pi_depth=1) -> str | None`: from
`GET wit/classificationnodes/Iterations?$depth=5`, collect nodes whose `attributes.startDate ≤ today ≤ finishDate`;
choose the shallowest such node at depth ≥ `pi_depth`; return its work-item-style path
(`Project\PI-14`, i.e. names joined by `\` without the "Iteration" segment). Classifier: `cfg.current_pi`
if set, else detected value passed by `classify_op` (fetched once and cached in the bug cache under `pi`).

## 6. Setup and status

New operations (`rca_core/operations/setup.py`):
- `status(cfg)` → `{signed_in, user, org_url, project, fields_ok, current_pi, tool_version}` (no network
  beyond token cache; `fields_ok` from cache of last `fields_op`).
- `login(cfg, complete=False)` → `{signed_in, user}` or device-flow instructions.
- `options(cfg, client)` → `{accounts: [name…], projects: [name…]}` (`profiles/me` → `accounts?memberId`;
  `{org}/_apis/projects`).
- `save_config(cfg, org_url=None, project=None, fields=None, current_pi=None)` → merges into
  `~/.rca/config.toml` (writes TOML with a minimal serializer; never touches auth secrets).
- `fields_op` gains `auto_map=True`: exact display-name or reference-name matches are written to the
  config automatically; only unresolved sections are returned as `issues`.

`/rca-setup` becomes: login → pick org (list; single → auto) → pick project (list; single → auto) → save
→ `fields_op(auto_map=True)` → ask only about `issues` → report. `/rca` calls `rca_status` first; if not
signed in or no project, it runs those setup steps inline, then proceeds.

## 7. Tools (MCP + CLI)

`rca_fetch(bug: str = "", pr_id=None)` (bug may be id, URL, or empty), `rca_trace(bug_id)`,
`rca_classify(bug_id)`, `rca_fields(auto_map=True)`, `rca_publish(bug_id, sections, dry_run=True)`,
`rca_status()`, `rca_login(complete=False)`, `rca_setup_options()`, `rca_save_config(org_url=None,
project=None, fields=None, current_pi=None)`. CLI mirrors them.

## 8. Errors (additions)

`not_signed_in`, `bug_not_resolved`, `no_fix_source` (no PR and cwd is not a git repo / branch is the
default branch), `history_unavailable` (ADO returned no history for a path).

## 9. Packaging

Version `0.2.0`; dependencies add `msal>=1.28`, `msal-extensions>=1.1`. Team defaults carry
`[auth] client_id`/`tenant_id` placeholders (`""`) — `rca_login` errors with code `auth_not_configured`
and a fix naming the two keys until they are filled. README updated: install → `/rca-setup` (sign in) →
`/rca`. The `.mcp.json` ref moves to `@v0.2.0` at release.

## 10. Testing

Fake transport routes for every new endpoint; a `FakeMsalApp` for auth; blame-emulation tests over a
synthetic 4-commit file history (introduce line, reformat whitespace, unrelated edit, base) asserting the
introducing commit wins and whitespace is ignored; branch containment via fake merge-base results;
`current_pi` over a synthetic iteration tree; `resolve_bug` over URL / id / branch cases with a
throwaway git repo for the branch name; setup `save_config` round-trip through `load_config`.
Local-branch fetch fallback keeps the v1 git-repo test. Live smoke test extended to `rca_trace`.

## 11. Out of scope

Rename-following in blame emulation; multi-repo fixes; auto-cloning; posting the RCA anywhere but the
Bug fields; GUI.
