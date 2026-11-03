# Evolve Lab — cloud agent migration, phase one

Evolve Lab contains a working Task Manager and an AI Developer Console. The backend now delegates development execution to an agent adapter. The default cloud adapter is a placeholder: it reports **not configured** and fails development requests explicitly. It does not call OpenAI, invoke the Codex CLI, create worktrees, edit source, or simulate successful changes.

## Run locally

Python 3.10+ is required; there are no Python dependencies. Node.js is needed for the JavaScript syntax check.

```bash
python3 server.py
```

Open http://127.0.0.1:8765. Task creation, listing, updates, and deletion work immediately. Task data persists in `runtime/state.json`. No API keys or Codex installation are needed. `POC_ALLOW_CODEX` no longer enables execution.

## Architecture

- `server.py`: HTTP routing, task persistence, asynchronous development jobs, and job events. `AGENT` supplies the development adapter.
- `agents/base.py`: `Agent` protocol (`status()` and `execute(request)`) and configuration error. Execution errors become failed jobs with an error event. Phase one deliberately has no successful artifact contract.
- `agents/cloud.py`: default `CloudAgent`; readiness is false and execution raises `AgentNotConfiguredError`. It has no SDK, credential loading, network calls, or local fallback.
- `dashboard.html`: Developer Console, including cloud readiness and job failures.
- `managed_app/`: Task Manager HTML, JavaScript, CSS, instructions, and smoke checks tracked directly in the main repository. Startup never initializes Git or changes Git configuration.
- `tests/test_server.py`: isolated backend and HTTP regression tests.
- `runtime/`: ignored local task data. Jobs and events remain in memory and disappear on restart.

The existing routes remain available:

| Route | Behavior |
| --- | --- |
| `GET /api/status` | Cloud adapter readiness; legacy `codexInstalled` and `codexEnabled` fields are false, `revision` is null (no Git lookup). |
| `GET/POST /api/tasks`, `PATCH/DELETE /api/tasks/<id>` | Task CRUD and persistence. |
| `POST /api/jobs` | Accepts a valid request with HTTP 202; the asynchronous job fails with an explicit cloud configuration error. |
| `GET /api/jobs`, `GET /api/jobs/<id>` | Job history, status, errors, and events. |
| `POST /api/jobs/<id>/approve` | HTTP 409: no reviewable change exists in this phase; local Git merging has been removed. |
| `/preview/<id>/...` | Preview route retained; HTTP 404 without a reviewable artifact. |
| `/`, `/app/...` | Developer Console and Task Manager assets. |

## Checks

```bash
python3 -m unittest discover -s tests -v
python3 managed_app/test_app.py
node --check managed_app/app.js
python3 -m py_compile server.py agents/__init__.py agents/base.py agents/cloud.py
```

## Later phases

A future cloud integration must define isolated execution, validated result artifacts, source changes through the main GitHub repository, review/approval semantics, persistent jobs, and deployment. No external agent service is connected in this phase. Never commit API keys or credentials; future configuration must use secure runtime secret injection.

This remains a single-user local prototype bound to loopback. Authentication, hardened remote execution, and production hosting are not implemented.
