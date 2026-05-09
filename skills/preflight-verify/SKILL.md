---
name: preflight-verify
description: Use when starting a new sprint, switching projects, or when agents keep hitting environment issues (wrong Python, missing Docker, broken paths). Scaffolds and verifies an executable environment contract so agents stop wasting tokens re-discovering where things are.
---

# Preflight Verify (Flight Check)

## What this solves

Agents burn tokens re-discovering environment facts every session: where Python lives, which test runner works, whether Docker is running, what shell is primary. The lesson-tracker captures retry-then-success patterns after the damage is done. The flight check prevents the damage: a machine-verifiable environment contract that agents read at startup and validators can re-run on demand.

## When to activate

- **Starting a new project** — run init to scaffold the contract from live probes
- **Starting a sprint** — run verify to confirm nothing drifted since last session
- **Agents hitting env friction** — check whether assertions exist for the failing area; if not, add one
- **After environment changes** — new Python version, Docker update, WSL config change → run verify
- **Debugging a subagent failure** — check if the handoff shows assertion failures

## How to use

### First time: scaffold the flight check

Run the init command from within the user's project. This creates
`.claude/flight-check.yaml` in the **current project directory**, not
in the plugin directory. It probes Python, Node, Docker, and WSL
automatically.

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" preflight-verify init
```

After init, review `.claude/flight-check.yaml` and adjust assertions
to match the project's actual needs. Add project-specific checks like
database connectivity, required API keys, or service health endpoints.

### Verify the environment

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" preflight-verify verify --radius all
```

Runs every assertion's `check_cmd` and matches output against
`expected_pattern`. Critical failures exit 1 and should block the sprint.
Non-critical failures are logged but pass through.

### Check status without re-running

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" preflight-verify status
```

Shows last verification results (which passed, which failed, when).

## What the hooks do automatically

These fire without user action — wired into hooks.json:

| Hook | Mode | Effect |
|------|------|--------|
| SessionStart | `inject` | Injects environment + project metadata as `additionalContext`. Stable = prompt cache hits. |
| PreToolUse (Task) | `inject-subagent` | Prepends assertions to subagent prompt. Workers know their contracts. |
| SubagentStop | `handoff-parse` | Auto-generates handoff from transcript if worker didn't write one. |

All hooks fail-open: no `flight-check.yaml` → emit `{}`, don't block.

## The flight-check.yaml file

Lives at `<project>/.claude/flight-check.yaml`. Four sections:

### `environment`

```yaml
environment:
  host_os: "Windows 11"
  shell_primary: "powershell"
  shells_available: ["powershell", "cmd", "wsl-bash"]
  container_runtime: "docker"
  notes: "WSL available but powershell is primary."
```

### `runtimes`

```yaml
runtimes:
  - id: "python"
    path: "C:\\Python314\\python.exe"
    check_cmd: "python --version"
    expected_pattern: "Python 3.14"
    critical: true
```

### `project`

```yaml
project:
  root: "C:\\Users\\you\\projects\\myapp"
  test_cmd: "uv run pytest"
  test_paths: ["services/api/tests"]
  notes: "Uses uv for Python execution."
```

### `assertions` — the executable contracts

```yaml
assertions:
  - id: "A-001"
    description: "Correct Python resolves on PATH"
    check_cmd: "python -c \"import sys; print(sys.executable)\""
    expected_pattern: "Python314"
    critical: true
    blast_radius: "global"
```

| Field | Purpose |
|-------|---------|
| `check_cmd` | Shell command that outputs verifiable text |
| `expected_pattern` | Regex against stdout+stderr. `"."` = any non-empty. |
| `critical` | `true` = failure blocks session |
| `blast_radius` | `global` / `project` / `hooks` — controls re-run frequency |

## Adding assertions

Good candidates for project-specific assertions:
- Database: `psql -c "SELECT 1"`
- API keys: `echo $API_KEY | head -c 4`
- Ports: `curl -s localhost:3000/health`
- Binaries: `which ffmpeg`
- Git clean: `git status --porcelain | wc -l` expected `"^0$"`

## Structured handoffs

Subagents should write `.claude/handoffs/handoff-<feature>-<ts>.yaml`:

```yaml
summary: >
  Implemented billing export. All assertions passed.
  Docker unreachable but non-blocking.

feature_id: "billing-export-v1"
assertions_checked:
  - id: "A-001"
    passed: true
    exit_code: 0
    output_snippet: "C:\\Python314\\python.exe"

commands_run:
  - cmd: "uv run pytest tests/test_export.py"
    exit_code: 0

left_undone: "Error handling for zero-row billing periods."
issues_discovered: "asyncio event loop conflict line 88."
```

If no handoff is written, SubagentStop auto-generates a minimal one.

## Design philosophy

**Adversarial validators.** Validators run `check_cmds` only — never
read project context. Stateless at the seam (consumer-driven contract
testing). Prevents cost bias from context poisoning.

**Executable over documentary.** Every assertion is a proof, not a claim.

**Blast radius controls cost.** Don't run expensive checks every session.

## Storage

- `<project>/.claude/flight-check.yaml`
- `<project>/.claude/handoffs/`
- Project-scoped. Survives clears, compacts, restarts.

## Dependencies

- Python 3.8+ (same python-finder as lesson-tracker)
- `pyyaml` recommended — falls back to JSON-only without it

## Related skills

`persistent-lesson-tracker`, `verification-before-completion`, `subagent-driven-development`
