# ADO RCA Assistant — Design Spec

Date: 2026-09-17
Status: Approved for planning

## 1. Purpose

A tool that, given an Azure DevOps (ADO) Bug ID, gathers the fix (linked PR or local branch), traces the
git history to the commit that introduced the defect, proposes the mandatory bug classification, drafts
every section of the team's RCA template, and after user confirmation writes each section to its field on
the Bug work item.

It is driven from Claude Code (`/rca <bug-id>`) and packaged so any teammate can install it and connect
it to their own ADO credentials and local clones.

## 2. RCA template (the output contract)

Every run must produce these sections. "Source" says where the content comes from.

| Section | Source |
|---|---|
| Summary of the Issue (developer point of view) | Written by Claude from bug title, repro steps, diff |
| Root Cause (specific logic / code block / environment factor) | Written by Claude from diff + culprit commit |
| Impact Assessment (modules, pages, features, data-integrity risk, client environments) | Written by Claude from area path, changed files, bug fields |
| Historical Context: Previous Versions (earliest version where bug exists) | `trace` (release branches containing culprit) |
| Historical Context: Related Identifiers (PRs, Bug/Feature/Task IDs) | `trace` (work items linked to culprit PR + fix PR) |
| Bug Classification: Legacy / Feature / Non-Feature | `classify`, confirmed by user |
| Preventive Action (concrete, actionable) | Written by Claude |
| Lesson Learned (specific technical or process gap) | Written by Claude |
| Analysis Method (how the issue was traced) | Written by Claude from the trace evidence chain |
| Fix Description (technical, not function-by-function) | Written by Claude from diff |
| Impacted Area | Area path + top-level folders/modules of changed files |
| Git commit that caused this issue | `trace` (top culprit SHA, author, date, PR) |
| Why the issue wasn't identified earlier | Written by Claude (test coverage of changed files, age of culprit, whether bug was environment-specific) |

Classification rules:

- **Legacy**: earliest release branch containing the culprit commit has version <= 9.6 (configurable cutoff).
- **Feature**: not Legacy, and the culprit commit's work-item chain (PR → linked work items → parents)
  reaches a Feature whose iteration path is under the current PI (configurable), or the user says so.
- **Non-Feature**: neither of the above.

The tool proposes; the user confirms. Confidence is reported as `high` / `medium` / `low` with a reason.

## 3. Architecture

One git repository, three deliverables:

```
ado-rca/
  pyproject.toml              # package "ado-rca", console scripts: rca, rca-mcp
  src/rca_core/               # pure logic, no I/O side effects beyond git/HTTP
    ado_client.py             # REST wrapper (work items, PRs, commits, fields, PATCH)
    git_forensics.py          # blame, commit lookup, release-branch containment
    classifier.py             # rule engine → proposal + confidence + reason
    fields.py                 # section ↔ field reference-name mapping, validation
    config.py                 # load/merge team defaults + ~/.rca/config.toml
    models.py                 # dataclasses for Bug, PR, Culprit, Evidence, Proposal
  src/rca_mcp/server.py       # FastMCP server exposing five tools
  src/rca_cli/main.py         # same five operations as CLI subcommands (JSON out)
  plugin/                     # Claude Code plugin
    .claude-plugin/plugin.json
    .mcp.json                 # runs: uvx --from <repo-url> rca-mcp
    skills/rca/SKILL.md
    skills/rca-setup/SKILL.md
  defaults/team.toml          # field map, branch pattern, cutoff, template text
  tests/
  docs/superpowers/specs/
```

Language: Python 3.11+. Dependencies: `requests`, `mcp` (FastMCP), `tomli`/`tomllib`. Nothing else.

### 3.1 Tools exposed (MCP and CLI share these signatures)

| Tool | Input | Output (compact JSON) |
|---|---|---|
| `rca_fetch` | `bug_id`, optional `pr_id` or `branch` | Bug fields (title, repro, area, iteration, environment/client, tags), linked PRs, fix commits, changed files with hunks (capped ~6 KB), fix PR's linked work items |
| `rca_trace` | `bug_id` (uses cached fetch) or explicit `repo` + `hunks` | Ranked culprits (max 3): SHA, author, date, message (first line), merging PR, linked work items with parent chain, release branches containing it, earliest version. Plus the evidence chain as ordered steps. Capped ~4 KB |
| `rca_classify` | trace output | `{proposal, confidence, reason, needs_confirmation}` |
| `rca_fields` | none | Bug work-item type fields: name, reference name, type, allowed values (for picklists). Validation result against the configured map |
| `rca_publish` | `bug_id`, `{section: value}`, `dry_run` | PATCH body (dry run) or updated work-item URL and revision |

`rca_fetch` and `rca_trace` write their results to `~/.rca/cache/<bug_id>.json` so later steps and reruns
don't refetch.

### 3.2 Skill `/rca <bug-id>`

Under 150 lines. Steps:

1. Call `rca_fetch`. If it returns `error`, show the fix instruction and stop.
   If no PR is linked and no branch given, ask the user for one.
2. Call `rca_trace`, then `rca_classify`.
3. Draft all sections using the table in §2. Rules for the narrative sections:
   - Root Cause names the specific condition (null path, missing filter, wrong join, etc.), not "a bug in X".
   - Fix Description stays at the level of behaviour changed, not function names.
   - Preventive Action must be a checkable action (a test to add, a lint rule, a review checklist item).
   - Lesson Learned must reference a gap found in this trace, not a generic statement.
4. Show the draft in chat with the classification proposal, its confidence and reason.
   Ask the user to confirm or correct the classification and edit anything else.
5. On confirmation, call `rca_publish` with `dry_run=false`. Report the work-item URL.

### 3.3 Skill `/rca-setup`

Run once per machine:

1. Ask for org URL, project name, and the name of the environment variable holding the PAT.
2. Call `rca_fields`; report any mapped section whose field is missing; propose the closest field by name
   and ask the user to accept or type another.
3. Ask for the local clone path of each repo (can be added later).
4. Write `~/.rca/config.toml`. Never write the PAT itself.

## 4. Git forensics (the core of `trace`)

For each changed hunk in the fix:

1. Take the *removed or modified* lines (pre-fix side). Run `git blame -w -M -C <base-sha> -L <start>,<end> -- <path>`
   in the local clone. `-w` ignores whitespace so formatting commits don't win.
2. Group blamed lines by commit. Rank commits by number of blamed lines across all hunks.
3. For each of the top 3: `git log -1` for author/date/message; find the PR that merged it via the ADO
   "pull requests by commit" API, falling back to parsing `Merged PR 1234:` from the merge commit reached
   by `git log --first-parent --ancestry-path`.
4. For the merging PR: linked work items; for each work item: walk `System.Parent` up to the Feature or
   Epic, recording ID, type, title, iteration path.
5. Release branches: `git branch -r --contains <sha>` filtered by the configured pattern
   (default `release/(\d+\.\d+)`). Parse versions, sort numerically, earliest is "Previous Version".
   If the culprit is only on `main`/`develop` and no release branch, report "unreleased" and mark
   classification confidence low.
6. If no hunk has removed lines (pure addition fix), blame the surrounding 3 lines and mark confidence low.

## 5. Classifier

Pure function `classify(trace, config) -> Proposal`.

```
if earliest_version is not None and earliest_version <= config.legacy_cutoff:
    Legacy, high (medium if only one culprit line)
elif any work item in chain is Feature and iteration startswith config.current_pi:
    Feature, high
elif chain reaches a Feature but PI unknown:
    Feature, low, needs_confirmation
else:
    Non-Feature, medium, needs_confirmation
```

`current_pi` is a string prefix in config (e.g. `PeoplesHR\PI-14`). If unset, Feature detection stays
low confidence and always asks.

## 6. Configuration

Merged in order: package `defaults/team.toml` → `~/.rca/config.toml` → environment variables.

```toml
[ado]
org_url = "https://dev.azure.com/peopleshr"
project = "PeoplesHR"
pat_env = "ADO_PAT"

[git]
release_branch_pattern = "release/(\\d+\\.\\d+)"
legacy_cutoff = "9.6"
current_pi = ""                     # iteration path prefix; empty = ask

[repos]
"PeoplesHR.Web" = "C:/src/PeoplesHR.Web"

[fields]                            # section key -> field reference name
summary = "Custom.RCASummary"
root_cause = "Custom.RootCause"
impact = "Custom.ImpactAssessment"
previous_versions = "Custom.PreviousVersions"
related_ids = "Custom.RelatedIdentifiers"
classification = "Custom.BugClassification"
preventive_action = "Custom.PreventiveAction"
lesson_learned = "Custom.LessonLearned"
analysis_method = "Custom.AnalysisMethod"
fix_description = "Custom.FixDescription"
impacted_area = "Custom.ImpactedArea"
culprit_commit = "Custom.CausingCommit"
why_missed = "Custom.WhyMissed"
```

The actual reference names are discovered with `rca_fields` during setup and stored in `team.toml`
once for the whole team.

## 7. Error handling

Every tool returns either a result or `{"error": {"code", "message", "fix"}}`. Codes:

`no_pat`, `auth_failed`, `bug_not_found`, `no_linked_pr`, `repo_not_configured`, `repo_not_cloned`,
`field_missing`, `field_type_mismatch`, `publish_rejected`. `fix` is a one-sentence instruction the skill
shows verbatim. The skill never retries silently.

## 8. Token control

- Hunks limited to changed lines plus 3 lines of context; total fetch payload capped at ~6 KB, trace at ~4 KB.
- Commit messages truncated to first line; work item titles to 80 chars.
- No file reads or repo exploration by Claude Code; everything comes from tool output.
- Target per run: about 10–15 K tokens including the draft.

## 9. Packaging and distribution

- `pyproject.toml` with console scripts `rca` and `rca-mcp`. Installed by `uvx --from git+<repo-url> rca-mcp`
  (plugin `.mcp.json`), so teammates need only `uv` installed.
- Plugin installed with `claude plugin add <repo-url>` (or marketplace entry pointing at the repo).
- Per-user config at `~/.rca/config.toml`; team defaults in the package. PAT only from an env var; never
  logged, never written.
- Semantic version in `pyproject.toml`; `/rca` shows a one-line notice when the repo has a newer tag.
- README with the two-line install and the `/rca-setup` walkthrough.

## 10. Testing

- **Unit**: classifier rules; version parsing from branch names; field-map validation; config merge order.
- **Git forensics**: tests build a throwaway repo (init, several commits, a `release/9.5` and `release/10.1`
  branch, one whitespace-only commit) and assert the expected culprit, ranking and earliest version.
- **ADO client**: recorded JSON fixtures for work item, PR, commits, fields, PATCH. One opt-in live smoke
  test gated by `RCA_LIVE=1`.
- **Publish**: `dry_run` returns the exact PATCH body; asserted against a golden file.
- **Skill**: manual end-to-end run on one real bug before tagging v0.1.0.

## 11. Out of scope (v1)

- Writing back to the PR description or wiki.
- Multi-repo fixes (a bug whose fix spans two repos): v1 handles the first repo and warns.
- Automatic detection of the current PI from the ADO iteration calendar (config value in v1).
- GitHub or non-ADO hosts.
