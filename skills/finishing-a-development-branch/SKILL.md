---
name: finishing-a-development-branch
description: Use ONLY at the end of a full plan/sprint when EVERY task is complete and tests pass — invoked once by subagent-driven-development or executing-plans after the final task, never after an individual task, mid-session, or whenever implementation "feels done". Guides merge/PR/keep/discard with archive-tagging so the feature branch is preserved for rewind/history.
---

# Finishing a Development Branch

## Overview

Guide completion of development work by presenting clear options and handling chosen workflow.

**Core principle:** Verify tests → Present options → Execute choice → Clean up.

**Announce at start:** "I'm using the finishing-a-development-branch skill to complete this work."

## The Process

### Step 1: Verify Tests

**Before presenting options, verify tests pass:**

```bash
# Run project's test suite
npm test / cargo test / pytest / go test ./...
```

**If tests fail:**
```
Tests failing (<N> failures). Must fix before completing:

[Show failures]

Cannot proceed with merge/PR until tests pass.
```

Stop. Don't proceed to Step 2.

**If tests pass:** Continue to Step 2.

### Step 1.5: Verify Wiring (End-to-End)

Passing unit tests are not proof the feature is *connected*. Before presenting options, verify the feature was wired to be fully functional for its intended purpose:

1. Identify the feature's real entry point — the UI action, CLI command, API route, or caller a user/consumer actually hits.
2. Confirm the path from that entry point reaches the new code end-to-end: there is an integration / e2e / smoke test that exercises it and passes, OR you manually traced and ran the real path and observed it work. Run it; paste the evidence (per super-radical-powers:verification-before-completion — no claims without fresh output).
3. State the result explicitly:
   - **Wired:** "Feature reachable end-to-end via <entry point>, verified by <command/observation>."
   - **Documented wiring exception:** if a real, external blocker prevents the full wire (an unreleased dependency, a pending product/credential decision, an open architecture question), that is acceptable — but you MUST surface it here and record it: what is not wired, the specific blocker, and the follow-up (issue/task) to close it. Carry this into the PR body / merge commit in Step 4.

**If the feature is unwired with no documented exception** — components built and unit-tested but never attached to their real entry point — STOP. This is the failure this gate exists to catch. Report it, then wire it (or get an explicit documented wiring exception from your human partner) before proceeding to options.

See `skills/shared/task-format-reference.md` for the wiring vocabulary.

### Step 2: Determine Base Branch

```bash
# Try common base branches
git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null
```

Or ask: "This branch split from main - is that correct?"

### Step 3: Present Options

Present exactly these 4 options:

```
Implementation complete. What would you like to do?

1. Merge back to <base-branch> locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work

Which option?
```

**Don't add explanation** - keep options concise.

### Step 4: Execute Choice

#### Option 1: Merge Locally (preserve branch + tag)

```bash
# Switch to base branch
git checkout <base-branch>

# Pull latest
git pull

# Merge feature branch with --no-ff so the branch context is preserved
# in the merge commit (even after the branch ref is gone, the merge
# commit shows where the work came from).
# Record the Step 1.5 wiring status in the merge commit — especially a
# documented wiring exception — so the record survives on the base branch.
git merge --no-ff <feature-branch> \
  -m "Merge <feature-branch>" \
  -m "Wiring: <Wired via <entry point>, verified by <command>  —OR—  Documented wiring exception: <what's unwired> / blocker: <blocker> / follow-up: <issue>>"

# Verify tests on merged result
<test command>

# Tag the merged work — this is the rewind/history anchor.
# The tag survives even if someone later deletes the branch,
# and it makes the merge point easy to find (`git tag -l "archive/*"`).
git tag -a "archive/<feature-branch>" -m "Merged <feature-branch> into <base-branch>"

# DO NOT delete the feature branch by default.
# Keeping it gives a named pointer for rewind and history navigation.
# Only delete if the human partner explicitly asks for cleanup, e.g.:
#   git branch -d <feature-branch>
# (The archive tag still preserves history in that case.)
```

Then: Worktree handling (Step 5) — keep worktree by default since branch is kept.

#### Option 2: Push and Create PR

```bash
# Push branch
git push -u origin <feature-branch>

# Create PR
gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
<2-3 bullets of what changed>

## Wiring Status
<"Wired end-to-end via <entry point>, verified by <command>" — OR — "Documented wiring exception: <what's unwired> / blocker: <blocker> / follow-up: <issue>">

## Test Plan
- [ ] <verification steps>
EOF
)"
```

Then: Cleanup worktree (Step 5)

#### Option 3: Keep As-Is

Report: "Keeping branch <name>. Worktree preserved at <path>."

**Don't cleanup worktree.**

#### Option 4: Discard

**Confirm first:**
```
This will permanently delete:
- Branch <name>
- All commits: <commit-list>
- Worktree at <path>

Type 'discard' to confirm.
```

Wait for exact confirmation.

If confirmed:
```bash
git checkout <base-branch>
git branch -D <feature-branch>
```

Then: Cleanup worktree (Step 5)

### Step 5: Cleanup Worktree

**For Option 4 (Discard):** Always remove the worktree.

**For Option 1 (Merge Locally):** Keep the worktree by default since the branch is kept. Only remove if the human partner explicitly requests cleanup.

**For Options 2 and 3:** Keep worktree.

Check if in worktree:
```bash
git worktree list | grep $(git branch --show-current)
```

If removing:
```bash
git worktree remove <worktree-path>
```

## Quick Reference

| Option | Merge | Push | Tag | Keep Branch | Keep Worktree |
|--------|-------|------|-----|-------------|---------------|
| 1. Merge locally | ✓ (--no-ff) | - | ✓ `archive/<name>` | ✓ | ✓ |
| 2. Create PR | - | ✓ | - | ✓ | ✓ |
| 3. Keep as-is | - | - | - | ✓ | ✓ |
| 4. Discard | - | - | - | - (force delete) | - |

## Common Mistakes

**Skipping test verification**
- **Problem:** Merge broken code, create failing PR
- **Fix:** Always verify tests before offering options

**Open-ended questions**
- **Problem:** "What should I do next?" → ambiguous
- **Fix:** Present exactly 4 structured options

**Automatic worktree cleanup**
- **Problem:** Remove worktree when the branch is still alive (Options 1, 2, 3)
- **Fix:** Only cleanup the worktree for Option 4 (Discard), or when the human partner explicitly asks after Option 1

**Deleting the feature branch on merge**
- **Problem:** `git branch -d <feature>` after merge removes the named pointer to the work, making rewind/history-navigation harder even though commits still exist on the base branch
- **Fix:** Default to keeping the branch and creating an `archive/<branch>` tag. Only delete on explicit request from the human partner.

**Fast-forward merge erases branch context**
- **Problem:** Plain `git merge` may fast-forward, leaving no merge commit to show the work came from a feature branch
- **Fix:** Always use `git merge --no-ff` in Option 1 so a merge commit records the integration point

**No confirmation for discard**
- **Problem:** Accidentally delete work
- **Fix:** Require typed "discard" confirmation

**Merging an unwired feature**
- **Problem:** Components built and unit-tested but never connected to their real entry point (never called, never attached to the UI). Tests are green; the feature does nothing.
- **Fix:** Run Step 1.5. Wire it, or record a documented wiring exception. Never merge an unwired feature silently.

## Red Flags

**Never:**
- Proceed with failing tests
- Merge without verifying tests on result
- Delete the feature branch on merge — keep it and add an `archive/` tag instead
- Use a fast-forward merge in Option 1 — always `--no-ff` to preserve branch context
- Delete work without confirmation
- Force-push without explicit request
- Invoke this skill mid-plan, after a single task, or "because implementation feels done" — only at end-of-plan after the final task
- Merge an unwired feature (built but not attached to its real entry point) without a documented wiring exception

**Always:**
- Verify tests before offering options
- Present exactly 4 options
- Create `archive/<feature-branch>` tag on Option 1 before any cleanup discussion
- Keep the feature branch on Options 1/2/3; only delete on Option 4 or explicit user request
- Get typed confirmation for Option 4
- Clean up worktree only for Option 4 (or Option 1 if user explicitly requests it)
- Run the Step 1.5 wiring gate before offering options; state "Wired" or a documented wiring exception

## Integration

**Called by:**
- **subagent-driven-development** (Step 7) - After all tasks complete
- **executing-plans** (Step 5) - After all batches complete

**Pairs with:**
- **using-git-worktrees** - Cleans up worktree created by that skill
