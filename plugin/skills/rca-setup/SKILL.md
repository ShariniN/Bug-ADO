---
name: rca-setup
description: "Sign in to Azure DevOps and set up ado-rca on this machine: pick org and project, map RCA fields, detect the PI."
---

# /rca-setup

Use only the `rca_*` tools. Never ask for or store a PAT or password.

1. `rca_status()`. If `auth_error` is set, show its `fix`. If the user has their own app registration IDs,
   `rca_save_config(client_id=…, tenant_id=…)`; otherwise offer PAT mode (same instructions as before). If no
   `auth_error`, go to step 2.
2. If not `signed_in`: say "Opening the Microsoft sign-in page in your browser…" then `rca_login()`.
   - If the result has `device_code_message`: show it verbatim, ask the user to reply when done, then `rca_login(complete=true)`.
   - Report `user`.
3. `rca_setup_options()`. If `accounts` has one entry use it; else list names and ask which. Save with
   `rca_save_config(org_url=<account url>)`. Call `rca_setup_options()` again; pick the project the same way
   and save it with `rca_save_config(project=<name>)`.
4. `rca_fields(auto_map=true)`. Report what was auto-mapped. For each remaining `issues[]` entry: show `section`,
   `configured`, `suggestion`, and the closest 5 field names from `fields[]`; ask the user to pick or type a reference
   name; then `rca_save_config(fields={section: ref})` and re-run `rca_fields(auto_map=true)` until `ok`.
5. Finish: `rca_status()` and print one line: signed in as <user>, <org>/<project>, fields ok, PI is detected per run.

If any tool returns `not_signed_in`, run step 2 (including the device-code branch) and retry that tool once.
