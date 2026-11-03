# Evolve Lab — Local Codex self-evolving application POC

This project is an **executable local proof of concept**, not a production system. It contains a working task manager, an AI Developer Console, a local development orchestrator, Git worktrees per request, independent smoke checks, preview links, and a **human approval step** before merging a change into the local app.

## 1. Run the application (no dependencies needed)

Prerequisites: Python 3.10+, Git, Node.js (used for JS syntax validation).

```bash
python3 server.py
```

Open **http://127.0.0.1:8765**. The Task Manager works immediately, even without an AI API key or Codex installed. You can add, complete, and delete tasks. Data is saved to `runtime/state.json`.

## 2. Enable real Codex code editing

Install and authenticate the official Codex CLI using the current instructions at https://developers.openai.com/codex/cli/ . For example, when npm access is available:

```bash
npm install -g @openai/codex
codex login
```

**Review the trust implications before enabling it.** Restart the local server with:

Linux/macOS:

```bash
POC_ALLOW_CODEX=1 python3 server.py
```

Windows PowerShell:

```powershell
$env:POC_ALLOW_CODEX="1"
python server.py
```

Open the Developer Console, enter a request, and click **Start development**. The server runs Codex in a new Git worktree under `runtime/workspaces/` using `codex exec --json --sandbox workspace-write --ask-for-approval never`. It independently validates with `node --check app.js` and `python3 test_app.py`, commits successful changes, and makes the proposed frontend available at `/preview/<job-id>/index.html`. Click **Approve locally** to fast-forward the local `main` branch. No changes are deployed to a hosting provider.

**Note:** The default demo request includes a backend data-model change that this frontend-only Codex worktree cannot perform fully. For the first actual coding run, use a frontend-only request like: **"Add an attractive dark mode switch to the existing task manager and store the preference in localStorage. Keep the existing task actions working."** This exercise tests real source editing, validation, preview, and approval. Backend migrations will be introduced in a later milestone.

## 3. Structure

- `dashboard.html` — AI Developer Console
- `server.py` — local-only HTTP backend and development task orchestrator
- `managed_app/` — versioned, Codex-editable application
- `managed_app/AGENTS.md` — instructions read by Codex
- `runtime/` — local task data and temporary worktrees (created on startup)

## 4. Scope and important limitations

- **Real functionality:** task CRUD, Git worktree creation, Codex invocation when enabled and installed, validation, status events, local preview, explicit approval/merge.
- **Not yet implemented:** user authentication, hosted Agents API, hardened sandboxing, isolated credentials, background job persistence, automated rollback, live deployment, backend code editing, production migration handling.
- The current review screen shows a change summary (`git diff --stat`), **not a line-by-line diff**.
- Workspaces use Git worktrees, which isolate source-control changes but **are not an operating-system security boundary**. For untrusted workloads, use a separate VM/container with restricted permissions and network access.
- Only run on loopback (`127.0.0.1`). Do not expose this HTTP server to the internet.
- Codex execution is **off by default**. It requires your explicit `POC_ALLOW_CODEX=1` flag and a valid Codex CLI login.
- Agent jobs and their event histories are in RAM and do not survive a server restart.
- Worktrees are not automatically cleaned up in this POC.
- The AI API itself has **not been invoked** as part of packaging this project; you must connect your own Codex installation to test an actual model-driven modification.

## 5. Self-test

```bash
python3 managed_app/test_app.py
node --check managed_app/app.js
python3 -m py_compile server.py
```

## 6. Next milestone

Replace the local CLI adapter with an Agents API or Codex app-server adapter, introduce isolated workers, robust review & diff, persistent state, backend schema migration, test coverage, and a reliable deployment mechanism.
