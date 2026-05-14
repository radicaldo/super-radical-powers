# Design: Claude Code Changelog Updates + Fork Rebrand

**Date:** 2026-05-13
**Scope:** Apply Claude Code v2.1.128–2.1.141 improvements to the Super Radical Powers plugin, plus rebrand docs and LICENSE from pcvelz/superpowers-extended-cc to this fork.

---

## Overview

Two parallel streams:

1. **Changelog updates** — Adopt new Claude Code hook and skill capabilities that improve safety, clarity, and feature coverage in this plugin.
2. **Rebrand** — Update README and LICENSE to reflect this as an independent personal fork (Super Radical Powers), removing stale references to pcvelz's marketplace/repo.

Approach: **B (renovate existing hooks + add new ones)**. Existing example hooks get updated to use the new `args: string[]` exec form. New hook examples are added for `continueOnBlock` patterns. Skill updates are inline additions only.

---

## Stream 1: Changelog Updates

### 1.1 New Hook Examples — `continueOnBlock` PostToolUse

**Files to create:**
- `hooks/examples/write-edit-guard.sh`
- `hooks/examples/bash-output-sniffer.sh`

#### `write-edit-guard.sh`

PostToolUse hook targeting `Write` and `Edit` tool calls. After a write or edit completes, checks two conditions:

1. **Size collapse:** reads size data directly from the tool input in the hook's stdin JSON.
   - For `Write`: the tool input contains `content` (the full new file). Check `line count < 20`.
   - For `Edit`: the tool input contains `old_string` and `new_string`. Flag if `old_string` has more than 3x the lines of `new_string`.
2. **Sensitive file:** matches the written `file_path` against recognized config patterns (`.env*`, `settings.json`, `*.yaml` in project root, `*.toml` in project root, `*.cfg`).

On match, exits 2 with a message. With `continueOnBlock: true` in the user's settings, the message feeds back to Claude mid-turn rather than stopping it.

Fail-open: any read or parse failure exits 0.

**README registration snippet** (to add under "Recommended Configuration"):

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

#### `bash-output-sniffer.sh`

PostToolUse hook targeting `Bash` tool calls. Reads the tool result output from the transcript and scans for known error patterns:

- `Permission denied`
- `command not found`
- `No such file or directory`
- `ModuleNotFoundError`
- `ENOENT`
- `Cannot find module`
- `Error: EPERM`

On match, exits 2 with a contextual hint keyed to the matched pattern (e.g. "Bash sniffer: 'Permission denied' detected — consider checking file ownership or using sudo."). With `continueOnBlock: true`, feeds back to Claude instead of blocking.

Fail-open: transcript missing or unreadable → exit 0.

**README registration snippet:**

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

---

### 1.2 Retrofit Existing Hooks to `args: string[]` Exec Form

**What changes:** Only the README's `settings.local.json` opt-in examples, not the `.sh` scripts or `hooks-cursor.json`.

- `hooks-cursor.json` — **no change needed.** It uses a relative `./hooks/session-start` path, not a `${CLAUDE_PLUGIN_ROOT}` placeholder, so there is no quoting problem to solve.
- README "Block Commits With Incomplete Tasks" example — update `"command": "bash ~/.claude/plugins/.../pre-commit-check-tasks.sh"` to `"args": ["/bin/bash", "${CLAUDE_PLUGIN_ROOT}/hooks/examples/pre-commit-check-tasks.sh"]`
- README "Block Low-Context Stop Excuses" example — same treatment

**Why:** Exec form bypasses shell interpretation of the path. The current README examples use hardcoded absolute paths that would need quoting if they contained spaces. Using `args: ["/bin/bash", "${CLAUDE_PLUGIN_ROOT}/..."]` passes the path directly to the OS without shell expansion, so no quoting required regardless of what `CLAUDE_PLUGIN_ROOT` expands to.

---

### 1.3 Skill Inline Additions

#### `skills/using-git-worktrees/SKILL.md`

Add a callout under **Creation Steps → 2. Create Worktree**:

> **`worktree.baseRef` (v2.1.133+):** By default, new worktrees now branch from `origin/<default>` (i.e. the remote default branch), not local `HEAD`. If you have unpushed commits on your current branch that you want included in the new worktree, set `worktree.baseRef: "head"` in your Claude Code settings.

#### `skills/dispatching-parallel-agents/SKILL.md`

Add a note in the agent dispatch section (wherever `subagent_type` is first mentioned):

> **Note:** `subagent_type` matching is case- and separator-insensitive as of v2.1.140. `"Code Reviewer"`, `"code_reviewer"`, and `"code-reviewer"` all resolve to the same agent type.

#### `skills/executing-plans/SKILL.md`

Add a tip near the continuous-run section (wherever the skill discusses multi-turn execution or checking in):

> **Tip:** For runs where you want Claude to work until a condition is met without manual check-ins, see `/goal` (v2.1.139+). Set a completion condition and Claude keeps working across turns. Works in interactive, `-p`, and Remote Control modes.

#### `update-config` plugin skill

The `update-config` skill lives outside this repo (it's a separate plugin), so we document these in the README under "Recommended Configuration" instead:

Add a "Skill Visibility" subsection documenting `skillOverrides` (`off` / `user-invocable-only` / `name-only`) and note that `Skill(name *)` permission rules now work as prefix match (v2.1.139+).

---

## Stream 2: Fork Rebrand

### 2.1 README.md

**Title and intro:**
- Change title to `# Super Radical Powers`
- Update subtitle to: "A personal fork of [pcvelz/superpowers-extended-cc](https://github.com/pcvelz/superpowers-extended-cc), itself a Claude Code-focused fork of [obra/superpowers](https://github.com/obra/superpowers)."

**Installation section:**
- Remove `/plugin marketplace add pcvelz/superpowers` — this fork has no public marketplace listing
- Replace with a local install instruction using Claude Code's `--plugin-dir` flag:
  ```bash
  # Clone the repo, then install for current session:
  claude --plugin-dir /path/to/super-radical-powers
  # Or add to your settings.json permanently via the plugin dir setting
  ```

**Support/Issues section:**
- Remove `https://github.com/pcvelz/superpowers/issues`
- Replace with: "For upstream issues, see [obra/superpowers](https://github.com/obra/superpowers/issues). For Claude Code-specific upstream, see [pcvelz/superpowers-extended-cc](https://github.com/pcvelz/superpowers-extended-cc/issues)."

**Contributing section:**
- Simplify to: "This is a personal fork. Improvements stay here. Anything that would benefit the broader Claude Code community gets considered for [pcvelz/superpowers-extended-cc](https://github.com/pcvelz/superpowers-extended-cc) upstream."

**Updating section:**
- Remove the `/plugin update superpowers-extended-cc@superpowers-extended-cc-marketplace` command (no longer valid for this fork)
- Replace with a `git pull` instruction

**Keep unchanged:**
- Fork lineage section ("The og fork's readme starts here")
- Visual comparison table
- All skill documentation
- Philosophy section
- `blog.fsck.com` upstream link

### 2.2 LICENSE

MIT requires preserving all existing copyright notices. Add a second line — do not remove Jesse Vincent's:

```
Copyright (c) 2025 Jesse Vincent
Copyright (c) 2025-2026 David Cummuta
```

No other changes to the MIT license text.

### 2.3 `docs/README.codex.md` and `docs/README.opencode.md`

Both already reference `obra/superpowers` only — no pcvelz references. No changes needed.

---

## Out of Scope

- `terminalSequence` hook output field — no concrete use case identified for this plugin; document if a use case emerges
- `$CLAUDE_EFFORT` in hooks — same; no current hook uses effort level
- `/feedback` command — submits feedback to Anthropic, not a context-management tool; no Superpowers action needed
- "Summarize up to here" in Rewind menu — built-in Claude Code UI feature, nothing to implement

---

## File Change Summary

| File | Action |
|---|---|
| `hooks/examples/write-edit-guard.sh` | Create |
| `hooks/examples/bash-output-sniffer.sh` | Create |
| `hooks-cursor.json` | Update `command` → `args` form |
| `README.md` | Rebrand + add new hook examples + args form + skill-visibility docs |
| `LICENSE` | Add David Cummuta copyright line |
| `skills/using-git-worktrees/SKILL.md` | Add `worktree.baseRef` callout |
| `skills/dispatching-parallel-agents/SKILL.md` | Add `subagent_type` case-insensitivity note |
| `skills/executing-plans/SKILL.md` | Add `/goal` tip |

---

## Success Criteria

- [ ] `write-edit-guard.sh` and `bash-output-sniffer.sh` are fail-open (exit 0 on any error)
- [ ] Both new hooks correctly read tool output from transcript JSON
- [ ] `continueOnBlock: true` is set in all example registration snippets for new hooks
- [ ] All `args: string[]` examples use `${CLAUDE_PLUGIN_ROOT}` placeholder, not hardcoded paths
- [ ] No pcvelz installation/support URLs remain in README
- [ ] LICENSE preserves Jesse Vincent's copyright notice above David Cummuta's
- [ ] Skill additions are additive only — no existing content removed or restructured
