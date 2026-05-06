---
name: persistent-lesson-tracker
description: Use when the same shell, file-edit, or environment friction keeps tripping up agents in this project — making main agents and subagents repeat fixes that were already discovered in earlier turns or sprints
---

# Persistent Lesson Tracker

## What this solves

Multi-agent flows in Claude Code have a recurring failure mode: every fresh subagent re-derives the same environment lessons. Where Python lives. That `python` is the Microsoft Store stub here and `py` is the real one. That this project's `pytest` needs `--no-cov`. That Docker volume mounts on Windows want `/c/path` not `C:\path`. The user ends up clicking "allow" on the same kinds of fixes 40+ times across a sprint.

This skill captures those lessons automatically as they happen and replays them into every new agent — main or subagent — at startup. The capture is structural, not text-mining: it watches actual tool call results and pairs failures with subsequent successes.

## Architecture

Four hook events, each doing one job:

**`PostToolUse` (matcher: `Bash|Write|Edit|MultiEdit`)** is the capture point. It receives the tool name, input, and response on stdin. If the call failed, it logs the failure to a small rolling buffer at `.claude/.lesson-buffer.json`. If the call succeeded and a similar call recently failed in this session, the diff between the two becomes a structured lesson written to `.claude/lessons.json`.

**`SubagentStop`** runs after every Task subagent finishes. Tool calls *inside* a subagent never fire the parent's PostToolUse, so we read the subagent's transcript via the `transcript_path` provided in the hook payload, walk it for the same retry-then-success pattern, and merge any new lessons into the project store.

**`SessionStart`** formats all stored lessons as natural-language hints (sorted by confidence — calls seen multiple times rank higher) and emits them as `additionalContext` so the main agent boots already knowing.

**`PreToolUse` (matcher: `Task`)** intercepts subagent dispatch, prepends the lessons block to the subagent's prompt via `updatedInput`, and also returns `additionalContext` as a fallback. The subagent boots with the lessons in front of it instead of re-discovering them.

## What gets captured

Lessons are structured, not free text:

```json
{
  "id": "a1b2c3d4e5",
  "tool": "Bash",
  "summary": "When using Bash here: `python --version` failed (...is not recognized...) — but `py --version` worked.",
  "what_failed": "python --version",
  "what_worked": "py --version",
  "error_excerpt": "Python was not found; run without arguments to install...",
  "source": "auto-postuse",
  "first_seen": "2026-05-06T...",
  "last_seen": "2026-05-06T...",
  "times_seen": 3
}
```

The `summary` is what gets injected; the rest is provenance. `times_seen` increments on each re-discovery and serves as a confidence score — high-confidence lessons rank first when there are more lessons than the inject cap (12).

## Storage

`.claude/lessons.json`, scoped to the project directory. Different projects accumulate different lesson sets — your Docker-heavy backend doesn't poison context for a pure Python data-science project.

The store survives session clears, compacts, restarts, and Claude Code updates. To reset: delete the file.

The total cap is 40 lessons; when exceeded, lowest-confidence + oldest entries drop. The injected window is 12, ranked by confidence.

A v1 lessons file (the original `learned_rules` schema) auto-migrates to v2 on first read; no manual conversion needed.

## Adding hand-curated rules

Edit `.claude/lessons.json` and add to `global_constraints`:

```json
"global_constraints": [
  "Never use sudo on this machine",
  "All shell commands must be pwsh-compatible — no bash-isms",
  "Use `py` instead of `python` (the latter is the Microsoft Store stub)"
]
```

These render at the top of the inject block and never expire — they bypass the FIFO trimming that applies to `learned_lessons`.

## Verification

After install or update, run `/hooks` inside Claude Code. You should see entries for `SessionStart`, `PreToolUse:Task`, `PostToolUse:Bash|Write|Edit|MultiEdit`, and `SubagentStop` pointing at `run-hook.cmd lesson-tracker ...`.

Smoke tests from a project root:

```bash
# Simulate SessionStart
"$CLAUDE_PLUGIN_ROOT/hooks/run-hook.cmd" lesson-tracker inject

# Simulate a PostToolUse capture (a failure followed by a success)
echo '{"tool_name":"Bash","tool_input":{"command":"python --version"},"tool_response":{"is_error":true,"stderr":"python: not found"}}' | "$CLAUDE_PLUGIN_ROOT/hooks/run-hook.cmd" lesson-tracker capture
echo '{"tool_name":"Bash","tool_input":{"command":"py --version"},"tool_response":{"is_error":false,"stdout":"Python 3.13"}}' | "$CLAUDE_PLUGIN_ROOT/hooks/run-hook.cmd" lesson-tracker capture
cat .claude/lessons.json
```

After the second capture, you should see a learned lesson pairing the two commands.

## Limitations and design choices

**Only Bash, Write, Edit, MultiEdit are watched.** These cover the bulk of friction-prone operations. Other tools (web fetch, MCP calls, etc.) aren't paired because their failure semantics vary too much for a generic heuristic. Easy to add — extend `is_failure` and `_input_signature` per-tool.

**The signature for retry detection is loose.** For Bash, two calls match if their first non-flag token matches (so `python script.py --foo` and `py script.py --foo` pair correctly). For file edits, it's the file path. False positives are possible but rare — and false positives just mean a slightly off lesson, not a crash.

**No transcript scanning of historical sessions.** The current design only learns from this session forward (plus subagent transcripts as they finish). Adding a SessionStart-time scan of `~/.claude/projects/<project>/*.jsonl` would bootstrap a project from prior history — a worthwhile extension but currently out of scope to keep startup fast.

**Lessons are project-scoped by design.** Environment quirks that genuinely apply across all projects (e.g. "this Windows install has a broken `python`") will get re-learned per-project. If you want them once-and-done, copy them to the user-level CLAUDE.md or add them to `global_constraints` manually.

## Related skills

`systematic-debugging`, `verification-before-completion`, `dispatching-parallel-agents`
