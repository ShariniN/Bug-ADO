---
name: rca-setup
description: "Sign in to Azure DevOps and set up ado-rca on this machine: pick org and project, map RCA fields, detect the PI."
---

# /rca-setup

Use only the `rca_*` tools. Never ask for or store a PAT or password.

1. `rca_status()`. If `auth_error.code == "auth_not_configured"`: show `auth_error.fix`. Ask "Do you have the
   ado-rca app registration's client ID and tenant ID from your Azure admin?"
   - If yes: collect both values and call `rca_save_config(client_id=<id>, tenant_id=<id>)`, then continue with step 2.
   - If no: offer PAT mode instead. Explain that the PAT needs **Work Items (read & write)** and **Code (read)**
     scopes, have them create it in Azure DevOps and run
     `[Environment]::SetEnvironmentVariable("ADO_PAT", "<token>", "User")`, then call
     `rca_save_config(auth_mode="pat")`. Tell them to restart Claude Code after setting the variable, and stop.
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
