# Native Task Format Reference

Skills that create native tasks (TaskCreate) MUST follow this format.

## Task Description Template

Every TaskCreate description MUST follow this structure:

### Required Sections

**Goal:** One sentence — what this task produces (not how).

**Files:**
- Create/Modify/Delete: `exact/path/to/file.py` (with line ranges for modifications)

**Acceptance Criteria:**
- [ ] Concrete, testable criterion
- [ ] Another criterion

**Verify:** `exact command to run` → expected output summary

### Optional Sections (include when relevant)

**Context:** Why this task exists, what depends on it, architectural notes.
Only needed when the task can't be understood from Goal + Files alone.

**Steps:** Ordered implementation steps (only for multi-step tasks where order matters).
TDD cycles happen WITHIN steps, not as separate steps.

## Metadata Schema

Embed metadata as a `json:metadata` code fence at the end of the TaskCreate description. The `metadata` parameter on TaskCreate is accepted but **not returned by TaskGet** — embedding in the description is the only reliable way.

| Key | Type | Required | Purpose |
|-----|------|----------|---------|
| `files` | string[] | yes | Paths to create/modify/delete |
| `verifyCommand` | string | yes | Command to verify task completion |
| `acceptanceCriteria` | string[] | yes | List of testable criteria |
| `estimatedScope` | "small" \| "medium" \| "large" | no | Relative effort indicator |

### Example

```yaml
TaskCreate:
  subject: "Add JIT selection prompt to /hame Pre-flight"
  description: |
    **Goal:** Replace auto-latest JIT selection with interactive 3-option prompt.

    **Files:**
    - Modify: `.claude/commands/hame-optimal-cycle-inspection.md:45-60`

    **Acceptance Criteria:**
    - [ ] AskUserQuestion presents 3 most recent JIT messages
    - [ ] Selected JIT's SOC and schedule are parsed into variables
    - [ ] --jit override bypasses the prompt (backwards compat)

    **Verify:** Read the Pre-flight Step 2 section and confirm AskUserQuestion block with 3 JIT options

    ```json:metadata
    {"files": [".claude/commands/hame-optimal-cycle-inspection.md"], "verifyCommand": "grep -A 20 'Step 2' .claude/commands/hame-optimal-cycle-inspection.md", "acceptanceCriteria": ["AskUserQuestion with 3 JIT options", "SOC + schedule parsed from selection", "--jit override bypasses prompt"]}
    ```
```

## End-to-End Wiring (Required Concept)

A plan is **wired** when the feature it builds is reachable and exercised through its real entry point — a user action flows UI → backend → response, or a caller actually invokes the new capability in production code. Plans that build and unit-test components in isolation but never connect them are **unwired**: every task is green, yet the feature does nothing for its intended purpose.

Three constructs prevent this. Skills MUST use these exact terms:

- **end-to-end wiring task** — a terminal task (the last in the plan, `blockedBy` every other task that contributes to the feature) whose job is to connect the pieces and prove the connection. Its `verifyCommand` MUST exercise the feature through its real entry point (an integration / e2e / smoke test, or an equivalent runtime check) — NOT a unit test that re-checks a single component. A plan that adds a new user-facing or cross-layer capability MUST contain one.

- **reachability check** — a self-review pass over the finished plan: for every new backend/capability, name the task that makes a caller invoke it; for every new UI affordance, name the task that connects it to a real backend call. A symbol that is defined by some task but called by none is the signature of an unwired plan. Add the missing wiring task or caller before finalizing.

- **documented wiring exception** — when the end-to-end wire genuinely cannot be completed inside this plan because of a real, external blocker (an unreleased upstream API, a credential or product decision not yet available, an architecture decision still open). Acceptable ONLY when recorded explicitly with: (1) what is not wired, (2) the specific blocker, (3) the follow-up that will close it (issue/task link). It must be surfaced, never silently passed.

A purely internal change with no new entry point (a refactor, a docs edit, a self-contained library function whose callers already exist) does not need a new wiring task — but the reachability check still applies: confirm existing callers still reach the changed code.

## Task Granularity

### The Right Scope

A task is **a coherent unit of work that produces a testable, committable outcome**.

**Scope test — ask these questions:**
1. Does this task produce something I can verify independently? (if no → too small)
2. Does it touch more than one concern? (if yes → too big)
3. Would it get its own commit? (if no → too small; if commit message needs bullet points → too big)

### Examples

| Scope | Example | Why |
|-------|---------|-----|
| Too small | "Write failing test for X" | Not independently verifiable — needs implementation |
| Too small | "Run pytest" | Verification step, not a task |
| Too small | "Add import statement" | Part of a larger change |
| **Right** | "Implement WebSocket protocol layer with tests" | Coherent unit, testable, one commit |
| **Right** | "Add JIT selection prompt to Pre-flight" | Single concern, verifiable, one commit |
| **Right** | "Create optimizer test class for SOC 73% case" | Complete test suite for one scenario |
| Too big | "Implement entire auth system" | Multiple concerns, multiple commits |
| Too big | "Fix all /hame output issues" | Multiple independent changes |

### TDD Within Tasks (Not Across Tasks)

TDD cycles (write test → verify fail → implement → verify pass) happen WITHIN a single task, not as separate tasks. The task is "Implement X with tests" — the TDD steps are execution detail, not task boundaries.

### Commit Boundary = Task Boundary

Each task should produce exactly one commit. If a task needs multiple commits, split it. If separate tasks share a commit, merge them.
