# ADO RCA Assistant v3 — Zero-setup sign-in, robustness, RCA quality

Date: 2026-09-18
Status: Approved (user)
Base: v2 spec, branch `feature/ado-rca` at tag v0.2.0. Patterns adopted from the internal phr-tcm app
(MSAL + PKCE through the Azure CLI public client; throttle-aware transport; batch reads; defect-type detection).

## 1. Sign-in without an app registration

- Team defaults: `auth.client_id = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"` (Azure CLI public client),
  `auth.tenant_id = "organizations"`. Own registration remains an optional override.
- `auth.persist_tokens = true` (default): DPAPI/keyring-encrypted cache as in v2. `false`: in-memory
  `SerializableTokenCache` only (phr-tcm model: sign in once per Claude Code session).
- `/rca-setup` no longer gates on `auth_not_configured` (it can still occur if a user blanks the ids).
- A 401/203 from Azure DevOps in browser mode removes the cached account from the MSAL cache and raises
  `not_signed_in` (fix: "Sign in again with rca_login"). PAT mode keeps `auth_failed`.

## 2. Transport robustness

- `RequestsTransport._send` honors `Retry-After` and `X-RateLimit-Delay` headers on every response
  (sleep min(value, 30 s) before returning; on 429 retry once after the delay). Sleep is injectable for tests.
- User-facing `message` never contains a URL or the raw response body; those go to `debug` (a second key
  inside `error` that the skill does not show unless asked). Shape: `{"error": {"code","message","fix","debug"}}`.
- `get_work_items` chunks ids into batches of 200.

## 3. Defect type detection

- `ado.bug_type = ""` (auto). `detect_bug_type()` probes `GET wit/workitemtypes` and picks `Bug` if present,
  else `Issue`, else the first type whose name contains "bug" (case-insensitive); cached in `status.json`.
  `bug_fields()` and `publish` use it; `resolve_bug` accepts that type name when scanning branch ids.

## 4. RCA quality

- **Existing RCA:** `fetch` reads the values of all mapped RCA fields on the bug (from the work item it already
  fetched); returns `existing_rca: {section: text}` for non-empty ones. `/rca` shows a one-line summary
  ("RCA already has 5 filled sections, last revised <date>") and asks: update (keep filled text as the starting
  point) or replace.
- **Test signal:** `trace` returns `test_signal: {fix_touched_tests: bool, culprit_pr_touched_tests: bool | None,
  test_paths: [..]}` using a path heuristic (`/test`, `/tests`, `.test.`, `.spec.`, `_test.`, `Tests/`).
  The `why_missed` drafting rule cites it. `culprit_pr_touched_tests` comes from the culprit PR's
  `diffs/commits` between its target and source commits (best-effort; None on error).
- **Publish gate:** dry run adds `warnings: [..]` — empty section; narrative sections (`summary, root_cause,
  impact, preventive_action, lesson_learned, analysis_method, fix_description, why_missed`) under 40 chars;
  `classification` not one of the three values (also an error when the field is a picklist). The skill shows
  warnings and asks before the live publish.

## 5. Packaging

Version `0.3.0`; `.mcp.json` `@v0.3.0`. README: sign-in "just works"; admin registration is an optional hardening
note; `persist_tokens` documented. Release procedure unchanged (fast-forward `main`, push, tag).

## 6. Testing

Fake transport gains header-driven throttle cases and a 401 case; MSAL fake verifies account removal;
chunking test with 450 ids → 3 calls; bug-type detection over three synthetic type lists; existing-RCA and
test-signal cases in fetch/trace tests; publish warnings table-driven.
