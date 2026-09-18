---
name: rca
description: "Fill the Azure DevOps Bug RCA from the fix. Usage: /rca [bug-id | work-item-url] [pr:<id>] — no argument infers the bug from the current branch"
---

# /rca — Bug RCA from the fix

You are filling the team's RCA template for Bug `$ARGUMENTS`. Use ONLY the `rca_*` MCP tools for data.
Do not read repo files or run git yourself; the tools already did the searching.

## 1. Ready?

1. `rca_status()`. If `configured` is false or `signed_in` is false, follow the rca-setup skill's steps inline
   (do not tell the user to run it) (login, org/project, fields) and continue.
2. Parse `$ARGUMENTS`: an id, a work item URL, `pr:<id>`, or nothing. Call
   `rca_fetch(bug=<id or url or "">, pr_id=<pr or null>, cwd=<the current working directory>)`.
   - `bug_not_resolved` / `no_fix_source`: show `message` and `fix`, then ask for the bug id or PR id and retry once.
   - Any other `error`: show `message` and `fix` and stop.
   - Tell the user how the bug was resolved (`resolved.how`) and which fix source was used (`source`, PR id if any).
   - If `truncated` is true, say the diff shown was partial. If `update_available`, print one line about it.
   - If `existing_rca` is non-empty: say how many sections are filled and that the bug last changed
     `<existing_rca_revised>`, then ask: update (start from the existing text for those sections) or replace.
     Wait for the answer.
3. `rca_trace(bug_id)`, then `rca_classify(bug_id)`. If `detected_pi` is set, mention it next to the proposal.

If any tool returns `not_signed_in`, call `rca_login()` (device-code branch as in step 1) and retry that tool once.

## 2. Draft

Write the RCA as a markdown draft with these headings, in this order. The keys in brackets are the section keys
you will publish. Keep each section tight; no filler.

- **Summary of the Issue** [summary] — developer's view: what fails, where, under which input. From bug title, repro steps, hunks.
- **Root Cause** [root_cause] — the specific condition: null path, missing filter, wrong join, off-by-one, race, config. Name the file and the pre-fix behaviour. Never write "a bug in X".
- **Impact Assessment** [impact] — modules/pages/features from `bug.area_path` and changed file folders; data-integrity risk (yes/no + why); client environments from `bug.extra` and `bug.tags`.
- **Previous Versions** [previous_versions] — `culprits[0].earliest_version` and its release branches. If none: "Unreleased (only on <target>)".
- **Related Identifiers** [related_ids] — fix PR id + title; culprit PR id + title; every work item in `work_items` and `parent_chain` as `Type ID: Title`. One per line.
- **Bug Classification** [classification] — exactly one of `Legacy Bug`, `Feature Bug`, `Non-Feature Bug`. Use the proposal.
- **Preventive Action** [preventive_action] — one checkable action: a named test to add, a lint/analyzer rule, a review-checklist line, a migration guard. Not "be more careful".
- **Lesson Learned** [lesson_learned] — the gap this trace exposed (e.g. "nullable column introduced in PR 7 without updating the two consumers"). Not generic.
- **Analysis Method** [analysis_method] — 3–5 lines from `evidence`: blamed lines at base, culprit ranked, PR found, chain, release branches.
- **Fix Description** [fix_description] — what behaviour changed, at the level of "now treats X as Y"; no function-by-function walkthrough.
- **Impacted Area** [impacted_area] — area path plus top-level folders of changed files, comma separated.
- **Causing Commit** [culprit_commit] — `<sha> — <date> — <author> — <subject> (PR <id>)`.
- **Why Missed Earlier** [why_missed] — concrete: no test covered the removed lines, culprit predates the client's config, only reproduces with data X, etc.
  Use `test_signal`: if `fix_touched_tests` is false say no test was added with the fix; if `culprit_pr_touched_tests`
  is false say the culprit PR added no tests; cite `test_paths` when true.

Then show, under the draft:

```
Classification proposal: <classification> (<confidence>) — <reason>
Notes: <each entry of confidence_notes from the rca_trace result on its own line, or "none">
```

## 3. Confirm

Ask: "Confirm the classification and the draft? Reply 'publish', or tell me what to change."
If `needs_confirmation` is true, say explicitly that the classification needs their call.
Apply requested edits and re-show only the changed sections. Do not publish until the user says publish.

## 4. Publish

1. Build `sections` = {section_key: plain text of that section} for all 13 keys. Plain text, no markdown headings.
2. Call `rca_publish(bug_id, sections, dry_run=True)`. On `error`, show `message` and `fix` and stop.
   If the dry run's `warnings` list is non-empty, show it and ask whether to publish anyway; only then call with `dry_run=False`.
3. Call `rca_publish(bug_id, sections, dry_run=False)`.
4. Report: `Published RCA to Bug <id> (rev <rev>): <url>`.
