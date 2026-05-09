# Preflight Verify — Quick Start Guide

A runnable environment contract system for super-radical-powers. Agents verify the environment before sprints, and re-verify when things drift.

---

## What problem does this solve?

Claude Code agents waste tokens re-discovering environment facts every session: where Python lives, what test runner to use, whether Docker is running. The lesson-tracker captures retry-then-success patterns, but environment facts aren't retries — they're stable truths that go stale silently.

The flight check turns those facts into **executable assertions**: a `check_cmd` + `expected_pattern` pair that any agent can run to *prove* the environment is correct. Not documentation that might be wrong — proof that updates itself.

---

## Setup (5 minutes)

### 1. Invoke the skill from Claude Code

The preflight-verify skill is a slash command in the plugin. In Claude Code, tell the agent:

> "Initialize a preflight flight check for this project"

Claude will invoke the `preflight-verify` skill and run:

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" preflight-verify init
```

This probes your current environment (Python version/path, Node, Docker, WSL) and scaffolds `.claude/flight-check.yaml` **in your project directory** — not in the plugin directory. The plugin provides the script; your project stores the contract.

Review the generated file and adjust assertions to match your project.

### 2. Verify it works

Ask Claude to verify, or it runs via the skill:

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" preflight-verify verify --radius all
```

You should see:

```
[preflight]   PASS  A-001 — Correct Python interpreter resolves on PATH [critical] (45ms)
[preflight]   PASS  A-002 — Project test suite passes baseline [critical] (3200ms)
[preflight]   PASS  A-003 — Docker daemon is reachable (120ms)
[preflight]   FAIL  A-004 — WSL shell accessible for cross-platform hooks (50ms)
[preflight] Flight check passed.
```

Non-critical failures don't block. Critical failures exit 1.

### 3. The hooks are already wired

`hooks.json` already includes the preflight-verify hooks:

| Hook | What it does |
|------|-------------|
| **SessionStart** → `inject` | Injects environment + project metadata as `additionalContext`. Stable content = prompt cache hits. |
| **PreToolUse (Task)** → `inject-subagent` | Prepends assertions to each subagent's prompt via `updatedInput`. Workers know their contracts. |
| **SubagentStop** → `handoff-parse` | If the worker didn't write a handoff YAML, extracts assertion pass/fail from the transcript as a fallback. |

All hooks fail-open: if `flight-check.yaml` doesn't exist yet, they emit `{}` and don't block.

---

## Path architecture: plugin vs. project

This is the key distinction:

| What | Where it lives | Why |
|------|----------------|-----|
| `preflight-verify.py` | `<plugin>/scripts/` | The script is part of the plugin — shared across all projects |
| `hooks/preflight-verify` | `<plugin>/hooks/` | Bash dispatch, same fail-open pattern as lesson-tracker |
| `skills/preflight-verify/SKILL.md` | `<plugin>/skills/` | The slash command definition |
| `flight-check.yaml` | `<your-project>/.claude/` | **Project-scoped** — each project has its own environment contract |
| `handoffs/` | `<your-project>/.claude/handoffs/` | **Project-scoped** — per-feature structured audit trails |

The script resolves the project directory via `CLAUDE_PROJECT_DIR` (set by Claude Code during hook execution) or `cwd` (set to the project during CLI invocation). It never writes to the plugin directory.

---

## The flight-check.yaml file

Lives at `<your-project>/.claude/flight-check.yaml`. Four sections:

### `environment` — what machine are we on?

```yaml
environment:
  host_os: "Windows 11"
  ide: "vscode"
  shell_primary: "powershell"
  shells_available: ["powershell", "cmd", "wsl-bash"]
  container_runtime: "docker"
  container_compose: true
  notes: "WSL available but powershell is primary."
```

### `runtimes` — what tools are installed?

```yaml
runtimes:
  - id: "python"
    path: "C:\\Python314\\python.exe"
    check_cmd: "python --version"
    expected_pattern: "Python 3.14"
    critical: true
```

### `project` — how does this codebase work?

```yaml
project:
  root: "C:\\Users\\you\\projects\\myapp"
  test_cmd: "uv run pytest"
  lint_cmd: "ruff check ."
  test_paths: ["services/api/tests", "apps/*/test"]
  notes: "Uses uv for Python execution."
```

### `assertions` — the executable contracts

```yaml
assertions:
  - id: "A-001"
    description: "Correct Python interpreter resolves on PATH"
    check_cmd: "python -c \"import sys; print(sys.executable)\""
    expected_pattern: "Python314"
    critical: true
    blast_radius: "global"
```

| Field | Purpose |
|-------|---------|
| `check_cmd` | Shell command that outputs something verifiable |
| `expected_pattern` | Regex matched against stdout+stderr. `"."` = any non-empty output |
| `critical` | `true` = failure blocks the session |
| `blast_radius` | `global` (every session), `project` (this project only), `hooks` (hook config changes only) |

---

## Structured handoffs

When a worker finishes a feature, it should write a handoff YAML to `<project>/.claude/handoffs/`:

```yaml
summary: >
  Implemented billing export. Switched from subprocess to asyncio.run().
  All assigned assertions passed. Docker unreachable but non-blocking.

feature_id: "billing-export-v1"
worker_session: "session-abc123"
assertions_assigned: ["A-001", "A-002", "A-003"]

assertions_checked:
  - id: "A-001"
    passed: true
    exit_code: 0
    output_snippet: "C:\\Python314\\python.exe"
  - id: "A-002"
    passed: true
    exit_code: 0
    output_snippet: "14 passed in 2.3s"
  - id: "A-003"
    passed: false
    exit_code: 1
    output_snippet: "error during connect"
    blocking: false

commands_run:
  - cmd: "uv run pytest services/api/tests/test_export.py"
    exit_code: 0

left_undone: "Error handling for zero-row billing periods."
issues_discovered: "asyncio event loop conflict in service_layer.py line 88."
procedures_followed: true
```

If a worker doesn't write a handoff, the SubagentStop hook auto-generates a minimal one (marked `_auto_generated: true`).

---

## Commands reference

All commands run via `run-hook.cmd` (handles Windows/Unix/WSL routing):

```bash
# Scaffold — creates flight-check.yaml in YOUR PROJECT's .claude/ directory
"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" preflight-verify init

# Verify — run assertions filtered by blast_radius
"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" preflight-verify verify
"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" preflight-verify verify --radius all
"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" preflight-verify verify --strict

# Status — last results without re-running
"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" preflight-verify status
```

The `inject`, `inject-subagent`, and `handoff-parse` modes are called automatically by the hooks — you don't invoke them manually.

---

## Hook flow diagram

```
SessionStart
  ├─ session-start           (upstream superpowers context injection)
  ├─ lesson-tracker inject   (learned lessons → additionalContext)
  └─ preflight-verify inject (env + project metadata → additionalContext)

PreToolUse (Task)
  ├─ lesson-tracker inject-subagent  (lessons → subagent prompt)
  └─ preflight-verify inject-subagent (assertions → subagent prompt)

PostToolUse (Bash|Write|Edit)
  └─ lesson-tracker capture  (watch for retry-then-success patterns)

SubagentStop
  ├─ lesson-tracker scan-subagent     (mine transcript for lessons)
  └─ preflight-verify handoff-parse   (extract assertion results)
```

---

## Architecture: why "stateless at the seams"

The flight check is designed around three patterns:

**Hexagonal architecture (ports and adapters)** — Each agent is a black box. The flight-check.yaml is the port. The `check_cmd` is the adapter. Nothing inside the box is the validator's business.

**Consumer-driven contract testing** — The validator (consumer) defines what correctness looks like via `expected_pattern`. The worker (provider) proves it delivers. The validator never reads implementation code.

**Design by Contract** — Assertions are preconditions. If they fail before a sprint, the sprint doesn't start. If they fail after a feature, it's a signal to scope corrective work.

Making validators adversarial *by architecture, not by prompting* is the key insight from Factory's multi-agent system. A validator that reads implementation context develops cost bias.

---

## Troubleshooting

**"flight-check.yaml not found"** — Run init first via the skill. The inject hooks fail-open if the file doesn't exist.

**"yaml module not installed"** — `pip install pyyaml --break-system-packages`. Falls back to JSON without it.

**Assertions timing out** — Default is 30s per `check_cmd`. Use `--tb=no -q` for test suites, or set `critical: false`.

**Auto-generated handoffs are low quality** — Expected. Train workers to write explicit handoffs by including the template in the assertion injection block. The auto-generator is the fallback.

**Prompt cache not hitting** — Flight check content must be injected in the same position every session. Keep hook order stable in `hooks.json`.
