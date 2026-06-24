# Super Radical Powers

> A Claude Code skills plugin — forked and extended to stop agents from wasting tokens in messy local environments, and to stop them from shipping features that were never actually wired up.

![version](https://img.shields.io/badge/version-5.5.0-6f42c1)
![license](https://img.shields.io/badge/license-MIT-3fb950)
![harnesses](https://img.shields.io/badge/harnesses-Claude%20Code%20%7C%20Cursor%20%7C%20Gemini%20%7C%20Codex-fb8c00)
![focus](https://img.shields.io/badge/focus-Windows%20%2B%20VS%20Code%20%2B%20subagents-1f6feb)
![built on](https://img.shields.io/badge/built%20on-superpowers-555)

A focused fork of [obra/superpowers](https://github.com/obra/superpowers), tuned for **Windows + VS Code + subagent-heavy workflows** — where the same environment facts get re-discovered every session and where "all tests pass" too often hides a feature that nobody ever connected to its real entry point.

---

##  Highlights

| | |
|---|---|
|  **End-to-end wiring gate** | Plans now end with a wiring task, and the merge gate refuses features that were built + unit-tested but never connected to a real entry point. |
|  **Persistent lesson tracker** | Environment lessons are injected into every agent and subagent at start. Learn once, stay learned — across sessions. |
|  **Preflight (flight check)** | An executable environment contract agents *prove* on demand, instead of caching probe results that go stale. |
|  **Parallel by default** | A worktree-isolated `implementer` agent plus planning nudges that fan independent work out into safe parallel waves. |
|  **Leaner plans** | Tighter, more actionable plans instead of 2000-line auto-transcription. |

## What's Radical Here

The core problem: agents on Windows repeatedly re-discover the same environment facts session after session. Where Python lives, which version `py` points to, what paths work. Every subagent starts fresh and burns 3-5 commands re-learning what the previous one already figured out. In VS Code this also means repeated permission prompts as each subagent starts without knowing what the previous task went through.

The second problem, just as expensive: a plan finishes with every task green, every unit test passing — and the feature still does nothing, because the pieces were built but never attached to the UI action, route, or caller a user actually hits. This fork treats that **unwired** state as a first-class failure and gates against it.

## What's New in v5.5.0 (June 2026)

### End-to-end wiring gate

> A plan is **wired** when the feature it builds is reachable and exercised through its real entry point — a user action flows UI → backend → response, or a caller actually invokes the new capability in production code. Plans that build and unit-test components in isolation but never connect them are **unwired**: every task is green, yet the feature does nothing for its intended purpose.

Three constructs now run through the planning and review skills, using one shared vocabulary:

- **End-to-end wiring task** — a terminal task (last in the plan, `blockedBy` every task that feeds the feature) whose `verifyCommand` exercises the feature through its real entry point — an integration / e2e / smoke test, not a unit test re-checking one component.
- **Reachability check** — a self-review pass: for every new backend capability, name the task that makes a caller invoke it; for every new UI affordance, name the task that connects it to a real backend call. A symbol defined by some task but called by none is the signature of an unwired plan.
- **Documented wiring exception** — when the wire genuinely can't be completed in this plan (unreleased upstream API, pending product/credential decision, open architecture question), that's acceptable **only** when recorded explicitly: what's not wired, the blocker, and the follow-up to close it. Surfaced, never silently passed.

Where it's enforced:

| Skill | What changed |
|---|---|
| `writing-plans` / `writing-plans-lite` | Require a terminal end-to-end wiring task and a reachability self-review before a plan is finalized. |
| `subagent-driven-development` / `requesting-code-review` | Final review adds a whole-implementation reachability check across the finished work. |
| `finishing-a-development-branch` | New **Step 1.5 wiring gate** before offering merge options; records wiring status in the PR body and merge commit; refuses to silently merge an unwired feature. |
| `shared/task-format-reference` | Canonical wiring vocabulary all the skills draw from. |

### More parallelism by default

- **New `implementer` agent** — a worktree-isolated implementation agent for parallel task execution. Each dispatch runs in its own temporary git worktree, so concurrent edits across a wave can't collide, with a strict file-ownership boundary that makes a worker stop and report rather than touch a sibling's files.
- **Planning nudges** — `writing-plans` and `subagent-driven-development` now push toward decomposing independent work into parallel-eligible waves instead of a single sequential chain.

### Smarter brainstorming options

When `brainstorming` proposes 2-3 approaches, each option now carries a rough **effort-level / time estimate** next to it, so you can weigh cost against value before choosing a direction.

<details>
<summary><strong>Earlier optimizations (v5.4 and before)</strong></summary>

- **Persistent lesson tracker** — hooks into the session lifecycle and injects environment lessons into every agent and subagent as they start. Agents learn once and stay learned, progressively across sessions.
- **Flight check (preflight-verify)** — an executable environment contract that agents verify before sprints and re-check when things drift, rather than caching probe results that go stale.
- **Leaner plan writing** — the upstream plan-writing skill was generating 2000+ line plans, burning tokens on essentially auto-transcription. Updated to write tighter, more actionable plans.
- **Less verbose "thinking"** — found underlying Claude Code thinking was extremely verbose, stuttering, and repeating itself. Fixed in the plan-writing skill; a faster "lite" variant writes smaller plans.
- **Post development branch fixes** — fixed `finishing-a-development-branch` firing inconsistently and always deleting the branch rather than asking or tagging.

</details>

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

1. **brainstorming** — Refines rough ideas through questions, explores alternatives, presents design in sections for validation. Each proposed approach now shows a rough effort/time estimate. Saves a design document.

2. **using-git-worktrees** — Creates an isolated workspace on a new branch, runs project setup, verifies a clean test baseline.

3. **writing-plans** — Breaks work into bite-sized tasks (2-5 minutes each). Every task has exact file paths, complete code, verification steps, and native task dependencies — plus a **terminal end-to-end wiring task** and a reachability self-review so a feature is never left built-but-disconnected.

4. **subagent-driven-development** or **executing-plans** — Dispatches a fresh subagent per task with two-stage review (spec compliance, then code quality), fanning parallel-eligible tasks into worktree-isolated waves where it can. Final review includes a whole-implementation reachability check. (Or run in batches with human checkpoints.)

5. **test-driven-development** — Enforces RED-GREEN-REFACTOR: write a failing test, watch it fail, write minimal code, watch it pass, commit. Deletes code written before tests.

6. **requesting-code-review** — Reviews against the plan, reports issues by severity, and checks the whole implementation is reachable end-to-end. Critical issues block progress.

7. **finishing-a-development-branch** — Verifies tests, runs the **end-to-end wiring gate** (Step 1.5) and records wiring status, then presents options (merge/PR/keep/discard) and cleans up the worktree.

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
- **test-driven-development** — RED-GREEN-REFACTOR cycle (includes testing anti-patterns reference)

**Debugging**
- **systematic-debugging** — 4-phase root cause process (includes root-cause-tracing, defense-in-depth, condition-based-waiting techniques)
- **verification-before-completion** — Ensure it's actually fixed

**Collaboration**
- **brainstorming** — Socratic design refinement + *native task creation*, with effort/time estimates on each option
- **writing-plans** — Detailed implementation plans + *native task dependencies* + *terminal wiring task & reachability self-review*
- **executing-plans** — Batch execution with checkpoints
- **dispatching-parallel-agents** — Concurrent subagent workflows
- **requesting-code-review** — Pre-review checklist + whole-implementation reachability check
- **receiving-code-review** — Responding to feedback
- **using-git-worktrees** — Parallel development branches
- **finishing-a-development-branch** — Merge/PR decision workflow + end-to-end wiring gate
- **subagent-driven-development** — Fast iteration with two-stage review (spec compliance, then code quality), with worktree-isolated parallel waves

**Meta**
- **writing-skills** — Create new skills following best practices (includes testing methodology)
- **using-superpowers** — Introduction to the skills system

### Agents

- **implementer** — Worktree-isolated implementation agent for parallel task execution. Runs one task from a wave in its own temporary git worktree, with a strict file-ownership boundary so concurrent edits never collide.
- **code-reviewer** — Reviews a completed step against the original plan and coding standards.

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

- **Test-Driven Development** — Write tests first, always
- **Wired, not just green** — A feature isn't done until it's reachable from its real entry point
- **Systematic over ad-hoc** — Process over guessing
- **Complexity reduction** — Simplicity as primary goal
- **Evidence over claims** — Verify before declaring success

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

MIT License — see LICENSE file for details

## Support

- **Issues**: https://github.com/radicaldo/super-radical-powers/issues

---

*Built on [obra/superpowers](https://github.com/obra/superpowers) and [pcvelz/superpowers](https://github.com/pcvelz/superpowers).*
