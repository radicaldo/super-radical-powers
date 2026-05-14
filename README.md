# Super Radical Powers

A Claude Code skills plugin, forked and extended with a focus on reducing token waste in messy local environments — especially Windows + VS Code + subagent-heavy workflows.

## What's Radical Here

The core problem: agents on Windows repeatedly re-discover the same environment facts session after session. Where Python lives, which version `py` points to, what paths work. Every subagent starts fresh and burns 3-5 commands re-learning what the previous one already figured out. In VS Code this also means repeated permission prompts as each subagent starts without knowing what the previous task went through.

Three fixes:

- **Persistent lesson tracker** — hooks into the session lifecycle and injects environment lessons into every agent and subagent as they start. Agents learn once and stay learned, progressively across sessions.
- **Flight check (preflight-verify)** — an executable environment contract that agents verify before sprints and re-check when things drift, rather than caching probe results that go stale.
- **Leaner plan writing** — the upstream plan-writing skill was generating 2000+ line plans, burning tokens on essentially auto-transcription. Updated to write tighter, more actionable plans.

## Installation

### Option 1: Via Marketplace (recommended)

```bash
# Register marketplace
/plugin marketplace add radicaldo/super-radical-powers

# Install plugin
/plugin install super-radical-powers@super-radical-powers-marketplace
```

### Option 2: Direct URL

```bash
/plugin install --source url https://github.com/radicaldo/super-radical-powers.git
```

### Verify Installation

```bash
/help
```

```
# Should see:
# /super-radical-powers:brainstorming - Interactive design refinement
# /super-radical-powers:writing-plans - Create implementation plan
# /super-radical-powers:executing-plans - Execute plan in batches
```

## The Basic Workflow

1. **brainstorming** - Refines rough ideas through questions, explores alternatives, presents design in sections for validation. Saves design document.

2. **using-git-worktrees** - Creates isolated workspace on new branch, runs project setup, verifies clean test baseline.

3. **writing-plans** - Breaks work into bite-sized tasks (2-5 minutes each). Every task has exact file paths, complete code, verification steps. Creates native tasks with dependencies.

4. **subagent-driven-development** or **executing-plans** - Dispatches fresh subagent per task with two-stage review (spec compliance, then code quality), or executes in batches with human checkpoints.

5. **test-driven-development** - Enforces RED-GREEN-REFACTOR: write failing test, watch it fail, write minimal code, watch it pass, commit. Deletes code written before tests.

6. **requesting-code-review** - Reviews against plan, reports issues by severity. Critical issues block progress.

7. **finishing-a-development-branch** - Verifies tests, presents options (merge/PR/keep/discard), cleans up worktree.

**The agent checks for relevant skills before any task.** Mandatory workflows, not suggestions.

## How Native Tasks Work

When `writing-plans` creates tasks, each task carries structured metadata that survives across sessions and subagent dispatch:

```yaml
TaskCreate:
  subject: "Task 1: Add price validation to optimizer"
  description: |
    **Goal:** Validate input prices before optimization runs.

    **Files:**
    - Modify: `src/optimizer.py:45-60`
    - Create: `tests/test_price_validation.py`

    **Acceptance Criteria:**
    - [ ] Negative prices raise ValueError
    - [ ] Empty price list raises ValueError
    - [ ] Valid prices pass through unchanged

    **Verify:** `pytest tests/test_price_validation.py -v`

    ```json:metadata
    {"files": ["src/optimizer.py", "tests/test_price_validation.py"],
     "verifyCommand": "pytest tests/test_price_validation.py -v",
     "acceptanceCriteria": ["Negative prices raise ValueError",
       "Empty price list raises ValueError",
       "Valid prices pass through unchanged"]}
    ```
```

The `json:metadata` block is embedded in the description because `TaskGet` returns the description but not the `metadata` parameter. This ensures metadata is always available — for `executing-plans` verification, `subagent-driven-development` dispatch, and `.tasks.json` cross-session resume.

## What's Inside

### Skills Library

**Testing**
- **test-driven-development** - RED-GREEN-REFACTOR cycle (includes testing anti-patterns reference)

**Debugging**
- **systematic-debugging** - 4-phase root cause process (includes root-cause-tracing, defense-in-depth, condition-based-waiting techniques)
- **verification-before-completion** - Ensure it's actually fixed

**Collaboration**
- **brainstorming** - Socratic design refinement + *native task creation*
- **writing-plans** - Detailed implementation plans + *native task dependencies*
- **executing-plans** - Batch execution with checkpoints
- **dispatching-parallel-agents** - Concurrent subagent workflows
- **requesting-code-review** - Pre-review checklist
- **receiving-code-review** - Responding to feedback
- **using-git-worktrees** - Parallel development branches
- **finishing-a-development-branch** - Merge/PR decision workflow
- **subagent-driven-development** - Fast iteration with two-stage review (spec compliance, then code quality)

**Meta**
- **writing-skills** - Create new skills following best practices (includes testing methodology)
- **using-superpowers** - Introduction to the skills system

### Preflight Verify (Flight Check)

An executable environment contract that agents verify before sprints and re-check when things drift. Solves the "stale environment facts" problem — instead of caching probe results that go stale, define assertions that *prove* the environment is correct on demand.

**How it works:**

1. Run `preflight-verify init` from any project root — it probes your environment (Python, Node, Docker, WSL) and scaffolds `.claude/flight-check.yaml`
2. At **SessionStart**, environment + project metadata is injected as `additionalContext` (stable content = prompt cache hits every session)
3. At **PreToolUse (Task)**, assertions are prepended to each subagent's prompt so workers know which correctness contracts they own
4. At **SubagentStop**, if the worker didn't write a structured handoff file, the script extracts assertion pass/fail signals from the transcript as a fallback
5. Run `preflight-verify verify --radius all` on demand to re-run all `check_cmds` and block on critical failures

**Flight check concepts:**

| Concept | Description |
|---------|-------------|
| **check_cmd** | Shell command that proves an assertion (e.g. `python --version`) |
| **expected_pattern** | Regex matched against stdout — `"."` means any non-empty output |
| **critical** | If `true`, failure blocks the session |
| **blast_radius** | `global` (every session), `project` (this project only), `hooks` (hook config changes only) |
| **Handoff** | Per-feature structured YAML: prose summary + assertions_checked array + commands_run + issues_discovered |

**Adversarial by design:** Validators run `check_cmds` only — they never read project context, lessons, or implementation code. Stateless at the seam, like a consumer-driven contract test.

**Example `flight-check.yaml`:**

```yaml
meta:
  schema_version: "1.0"
  project: "cloudcost"
  generated_at: "2026-05-08T10:00:00Z"

environment:
  host_os: "Windows 11"
  shell_primary: "powershell"
  container_runtime: "docker"

runtimes:
  - id: "python"
    path: "C:\\Python314\\python.exe"
    check_cmd: "python --version"
    expected_pattern: "Python 3.14"
    critical: true

assertions:
  - id: "A-001"
    description: "Correct Python interpreter resolves on PATH"
    check_cmd: "python -c \"import sys; print(sys.executable)\""
    expected_pattern: "Python314"
    critical: true
    blast_radius: "global"
  - id: "A-002"
    description: "Project test suite passes baseline"
    check_cmd: "uv run pytest --tb=no -q"
    expected_pattern: "passed"
    critical: true
    blast_radius: "project"
```

**Scripts:** `scripts/preflight-verify.py` (6 modes: init, verify, inject, inject-subagent, handoff-parse, status)  
**Hooks:** `hooks/preflight-verify` (bash dispatch, same fail-open pattern as lesson-tracker)  
**Docs:** `docs/enhancements.md` (full schema, handoff format, architecture rationale)

## Philosophy

- **Test-Driven Development** - Write tests first, always
- **Systematic over ad-hoc** - Process over guessing
- **Complexity reduction** - Simplicity as primary goal
- **Evidence over claims** - Verify before declaring success

## Recommended Configuration

### Disable Auto Plan Mode

Claude Code may automatically enter Plan mode during planning tasks, which conflicts with the structured skill workflows in this plugin. To prevent this, add `EnterPlanMode` to your permission deny list.

**In your project's `.claude/settings.json`:**

```json
{
  "permissions": {
    "deny": ["EnterPlanMode"]
  }
}
```

This blocks the model from calling `EnterPlanMode`, ensuring the brainstorming and writing-plans skills operate correctly in normal mode. See [upstream discussion](https://github.com/anthropics/claude-code/issues/23384) for context.

### Block Commits With Incomplete Tasks

Optional `PreToolUse` hook that blocks `git commit` while a native task is `in_progress`. Pending tasks pass through, so per-task commit flows work as intended.

Opt in via `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "args": ["/bin/bash", "${CLAUDE_PLUGIN_ROOT}/hooks/examples/pre-commit-check-tasks.sh"]
          }
        ]
      }
    ]
  }
}
```

See the header of `hooks/examples/pre-commit-check-tasks.sh` for how it parses the session transcript and which task states count as open.

### Block Low-Context Stop Excuses

Optional `Stop`-event hook that blocks "fresh session later" / "context is full" deflections when real context usage is below 50%.

Opt in via `.claude/settings.local.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "args": ["/bin/bash", "${CLAUDE_PLUGIN_ROOT}/hooks/examples/stop-deflection-guard.sh"]
          }
        ]
      }
    ]
  }
}
```

See the header of `hooks/examples/stop-deflection-guard.sh` for the full list of blocked phrases, configuration environment variables, and fail-open behavior.

### Guard Writes and Edits

Optional `PostToolUse` hook that warns when a `Write` produces fewer than 20 lines or an `Edit` removes 3x more lines than it adds. Also flags writes to recognized config files (`.env*`, `settings.json`, `*.yaml`, `*.yml`, `*.toml`, `*.cfg`). With `continueOnBlock: true`, the warning feeds back to Claude mid-turn rather than stopping it.

Opt in via `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "continueOnBlock": true,
            "args": ["/bin/bash", "${CLAUDE_PLUGIN_ROOT}/hooks/examples/write-edit-guard.sh"]
          }
        ]
      }
    ]
  }
}
```

See the header of `hooks/examples/write-edit-guard.sh` for configuration details and fail-open behavior.

### Sniff Bash Output for Errors

Optional `PostToolUse` hook that scans Bash tool output for common error patterns (`Permission denied`, `command not found`, `No such file or directory`, `ModuleNotFoundError`, `ENOENT`, `Cannot find module`, `Error: EPERM`) and injects a pattern-specific recovery hint back to Claude.

Opt in via `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "continueOnBlock": true,
            "args": ["/bin/bash", "${CLAUDE_PLUGIN_ROOT}/hooks/examples/bash-output-sniffer.sh"]
          }
        ]
      }
    ]
  }
}
```

See the header of `hooks/examples/bash-output-sniffer.sh` for the full pattern list and fail-open behavior.

### Skill Visibility

Control which skills Claude can invoke using `skillOverrides` in your Claude Code settings. Three values are supported:

- `"off"` — skill is completely hidden from Claude (cannot be invoked at all)
- `"user-invocable-only"` — skill is only available when the user explicitly types the slash command
- `"name-only"` — skill is visible by name in listings but Claude cannot read the full skill content

**In your project's `.claude/settings.json`:**

```json
{
  "skillOverrides": {
    "super-radical-powers:brainstorming": "user-invocable-only",
    "super-radical-powers:writing-plans": "user-invocable-only"
  }
}
```

**Wildcard prefix rules (v2.1.139+):** `Skill(name *)` patterns in permission rules now work as prefix matches. To allow all skills in this plugin, add to your project's `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": ["Skill(super-radical-powers:*)"]
  }
}
```

## Updating

```bash
/plugin update super-radical-powers@super-radical-powers-marketplace
```

## License

MIT License - see LICENSE file for details

## Support

- **Issues**: https://github.com/radicaldo/super-radical-powers/issues

---

*Built on [obra/superpowers](https://github.com/obra/superpowers) and [pcvelz/superpowers](https://github.com/pcvelz/superpowers).*
