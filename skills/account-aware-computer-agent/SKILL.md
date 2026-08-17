---
name: account-aware-computer-agent
description: Use when a task requires a specific signed-in account, browser automation, attachment downloads, or handing control to the user for authentication before resuming the same session.
---

# Account-Aware Computer Agent

## Overview
Use native connectors first, but verify the authenticated account before reading user data. If the connector is bound to the wrong account, switch to the persistent computer MCP rather than searching the wrong mailbox or claiming the data is absent.

## Required workflow

1. **Verify connector identity before searching account-specific data.** For Gmail, call `get_profile` first whenever the user names or implies a specific mailbox.
2. If the connector profile matches the requested account, use Gmail search/read tools and `read_attachment` directly.
3. If the connector profile does **not** match, stop using that connector for the task. Do not treat zero results as evidence the message does not exist.
4. Use the persistent computer MCP when available:
   - `computer_start` or `computer_status`
   - navigate to the signed-in service
   - verify the visible account identity before reading data
   - use `computer_handoff` when login, OAuth, MFA, CAPTCHA, password-manager, or other user-only authentication is required
   - preserve the same browser session after handoff
   - resume automation after the user finishes authentication
5. For browser-hosted attachments, use `computer_download` and then `computer_list_downloads`; return the saved file path to the calling agent.
6. Never request or store a user's password in the skill. Authentication is completed by the user during handoff.
7. If neither the correct connector nor the persistent computer MCP is available in the current runtime, state the precise missing capability: **the requested account binding is not exposed in this runtime**. Do not say the email or attachment does not exist.

## Persistent browser configuration

The MCP supports a persistent profile and an optional existing Chrome/CDP session:

- `PW_USER_DATA_DIR` — persistent Chromium profile directory.
- `PW_DOWNLOAD_DIR` — attachment/download destination.
- `PW_HEADLESS=false` — keep a visible browser for local handoff.
- `PW_CDP_ENDPOINT` — optional Chrome remote-debugging endpoint for attaching to an already running signed-in browser.
- `PW_VIEWER_URL` — optional WebViewer/noVNC URL returned by `computer_handoff` for mobile/remote handoff.
- `PW_EXPECTED_GOOGLE_ACCOUNT` — expected Google account, e.g. `satcomwarrior@gmail.com`.

## Gmail example

When the user says an attachment is in `satcomwarrior@gmail.com`:

- call Gmail `get_profile` first;
- if it returns another mailbox, do not search it;
- start the persistent computer, open Gmail, verify `satcomwarrior@gmail.com`, hand off for auth only if required, resume, locate the message, and download the attachment;
- preserve the downloaded file as source evidence for the downstream task.

## Common failure this skill prevents

Searching the default Gmail connector without checking its profile can silently query the wrong mailbox. A zero-result search from the wrong account is not a valid search result for the requested account.
