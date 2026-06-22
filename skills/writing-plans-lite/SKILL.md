---
name: writing-plans-lite
description: Use when you need a concise implementation plan for a multi-step task before touching code; favors short, actionable tasks over exhaustive code inlining
---

# Writing Plans Lite

## Critical Constraints

**You MUST NOT call `EnterPlanMode` or `ExitPlanMode` at any point during this skill.** This skill operates in normal mode and manages completion via `AskUserQuestion`. Calling `EnterPlanMode` traps the session in plan mode where Write/Edit are restricted. Calling `ExitPlanMode` breaks the workflow and skips the user's execution choice.

Do not use prior plan documents as style templates. Use them only for context.

Do not narrate drafting, "thinking out loud", or imagined implementation. Never emit filler such as "Writing test cases...", present-tense play-by-play, or repeated checklist items. Think silently and return the plan.

## Overview

Write concise implementation plans for skilled engineers who need repo-specific direction, not generic software advice. Focus on file ownership, interfaces, acceptance criteria, dependencies, and verification commands.

Prefer the smallest artifact that makes the task unambiguous:
- file lists and responsibilities
- interfaces, signatures, schemas, and sample payloads
- exact test cases and verify commands
- short notes for risky logic or non-obvious edge cases

Do not auto-transcribe full implementations or expand TDD ritual into every task unless the logic is fragile enough to justify it.

**Announce at start:** "I'm using the writing-plans-lite skill to create the implementation plan."

**Context:** This should be run in a dedicated worktree created by brainstorming.

**Save plans to:** `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`
- User preferences for plan location override this default.

If the user wants an exhaustive, highly inlined plan, use the original `writing-plans` skill instead.

## Scope Check

If the spec covers multiple independent subsystems, suggest separate plans. Each plan should produce working, testable software on its own.

## Plan Shape

Before defining tasks, map which files will be created or modified and what each one is responsible for.

- Prefer focused files with one clear responsibility.
- Keep files that change together close together.
- Follow existing repo structure unless there is a clear reason to split a file.

## Plan Length Target

Target 150-350 lines.

Up to 500 lines is acceptable for larger efforts with real complexity. If the plan wants to exceed that, split it into sub-plans or remove unnecessary inlining.

## Required First Step: Initialize Task Tracking

**Before exploring code or writing the plan, you MUST:**

1. Call `TaskList` to check for existing tasks from brainstorming.
2. If tasks exist, enhance them with implementation details as you write the plan.
3. If no tasks exist, create them with `TaskCreate` as you write each plan task.

**Do not proceed to exploration until `TaskList` has been called.**

```text
TaskList
```

## Task Granularity

Each task should be one coherent, verifiable, committable slice.

Use this scope test:
1. Can it be verified independently?
2. Would it plausibly be one commit?
3. Is it focused on one concern?

If a task fails one of those checks, merge it with an adjacent task or split it.

## Wiring / Integration Task (Required)

A plan that adds a new user-facing or cross-layer capability MUST end with an **end-to-end wiring task** — the final task that connects the pieces and proves the feature works through its real entry point. Its **Verify** must exercise the feature end-to-end (integration / e2e / smoke), not re-run a single component's unit test. Without it, plans ship "built but never attached to the UI."

If a real external blocker prevents the full wire, record a **documented wiring exception** (what's unwired, the blocker, the follow-up) instead of dropping it. Pure internal changes with no new entry point may skip the wiring task, but the reachability check below still applies. See `skills/shared/task-format-reference.md`.

## Plan Document Header

Every plan must start with this header:

```markdown
# [Feature Name] Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use super-radical-powers:subagent-driven-development (recommended) or super-radical-powers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

## Task Structure

Use this lighter task shape:

````markdown
### Task N: [Short Title]

**Goal:** [One sentence describing the outcome]

**Files:**
- Create: `exact/path/to/new-file.ts`
- Modify: `exact/path/to/existing-file.ts`
- Test: `tests/exact/path/to/test-file.test.ts`

**Acceptance Criteria:**
- [ ] [Concrete, testable criterion]
- [ ] [Concrete, testable criterion]

**Verify:** `exact command`

**Implementation Notes:**
- [Exact interfaces, data contracts, state transitions, or edge cases]
- [Short note only when needed]

**Steps:**
- [ ] Add or update tests covering: [exact behaviors]
- [ ] Implement [module/function/component] with these interfaces:

```ts
export interface Example {
  id: string;
}

export function buildExample(input: Input): Example;
```

- [ ] Run `pnpm test path/to/test-file.test.ts` until green
- [ ] Commit with `feat: add example behavior`
````

Inline full test code only when behavior is subtle, brittle, or easy to misunderstand. Otherwise list the exact test cases and required assertions.

Inline full implementation only when the logic is fragile or non-obvious, such as tricky SQL, state machines, parsing rules, or config gotchas.

## No Placeholders

Every task must still be unambiguous. These are plan failures:
- `TBD`, `TODO`, `implement later`, `fill in details`
- `Add validation`, `handle edge cases`, `write tests for the above`
- `Similar to Task N`
- references to types, functions, flags, or files not defined anywhere in the plan

## Brevity Rules

- Prefer signatures, schemas, sample inputs, and acceptance criteria over full code.
- Do not repeat the same verify or commit boilerplate in expanded prose.
- Do not restate obvious framework knowledge the implementer already knows.
- Do not simulate coding in present tense.
- Cut anything that does not change what the implementer will actually do.

## Self-Review

After writing the plan, do a short self-review:

1. Spec coverage: every requirement maps to a task or note.
2. Placeholder scan: remove vague language.
3. Type consistency: names and interfaces match across tasks.
4. Concision pass: remove generic explanation and repeated boilerplate.
5. Reachability (wiring) check: every new capability has a task wiring a real caller to it (UI affordance → real backend call; new endpoint/service → a caller). A symbol defined but never called = unwired; add the wiring task or a documented wiring exception.

If you find gaps, fix them inline.

## Execution Handoff

<HARD-GATE>
STOP. You are about to complete the plan. DO NOT call EnterPlanMode or ExitPlanMode. You MUST call AskUserQuestion below.
</HARD-GATE>

Your only permitted next action is calling `AskUserQuestion` with this exact structure:

```yaml
AskUserQuestion:
  question: "Plan complete and saved to docs/superpowers/plans/<filename>.md. How would you like to execute it?"
  header: "Execution"
  options:
    - label: "Subagent-Driven (this session)"
      description: "I dispatch fresh subagent per task, review between tasks, fast iteration"
    - label: "Parallel Session (separate)"
      description: "Open new session in worktree with executing-plans, batch execution with checkpoints"
```

**If you are about to call ExitPlanMode, STOP and call AskUserQuestion instead.**

<HARD-GATE>
STOP. The user has chosen an execution method. You MUST invoke the corresponding skill using the Skill tool NOW. Do NOT implement tasks yourself.

**If Subagent-Driven chosen:**
Invoke the Skill tool: `super-radical-powers:subagent-driven-development`

**If Parallel Session chosen:**
Guide the user to open a new session in the worktree, then invoke: `super-radical-powers:executing-plans`
</HARD-GATE>

---

## Native Task Integration Reference

For each plan task, create a matching native task. Keep the description concise and embed metadata as a `json:metadata` code fence so it survives `TaskGet`.

```yaml
TaskCreate:
  subject: "Task N: [Short Title]"
  description: |
    **Goal:** [From task goal]

    **Files:**
    [From task files]

    **Acceptance Criteria:**
    [From task acceptance criteria]

    **Verify:** [From task verify line]

    ```json:metadata
    {"files": ["path/to/file.ts"], "verifyCommand": "pnpm test path/to/test.ts", "acceptanceCriteria": ["criterion 1", "criterion 2"]}
    ```
  activeForm: "Implementing [Short Title]"
```

If a task depends on another task, set `blockedBy` after creation.

```text
TaskUpdate:
  taskId: [task-id]
  addBlockedBy: [prerequisite-task-ids]
```

During execution, update status normally:

```text
TaskUpdate:
  taskId: [task-id]
  status: in_progress

TaskUpdate:
  taskId: [task-id]
  status: completed
```

## Task Persistence

At plan completion, write the task persistence file in the same directory as the plan document.

If the plan is saved to `docs/superpowers/plans/2026-01-15-feature.md`, the tasks file must be saved to `docs/superpowers/plans/2026-01-15-feature.md.tasks.json`.

```json
{
  "planPath": "docs/superpowers/plans/2026-01-15-feature.md",
  "tasks": [
    {
      "id": 0,
      "subject": "Task 0: ...",
      "status": "pending",
      "description": "**Goal:** ...\n\n```json:metadata\n{\"files\": [\"path/to/file.ts\"], \"verifyCommand\": \"pnpm test path/to/test.ts\", \"acceptanceCriteria\": [\"criterion 1\"]}\n```"
    }
  ],
  "lastUpdated": "<timestamp>"
}
```

Any new session can resume with:

```text
/super-radical-powers:executing-plans <plan-path>
```
