#!/usr/bin/env python3
"""
Lesson Tracker v2 for super-radical-powers Claude Code plugin.

The premise is simple: when a tool call fails and a similar one later
succeeds, the difference between them IS the lesson. We capture that
in real time via PostToolUse instead of mining conversation text.

Hook events handled (each via a separate sub-command):

  inject              SessionStart hook.
                      Format all stored lessons as natural language and
                      emit them as additionalContext for the main agent.

  inject-subagent     PreToolUse hook with matcher "Task".
                      Read the Task tool's input from stdin, prepend the
                      lessons block to the subagent's prompt via
                      updatedInput, and also send additionalContext as a
                      fallback.

  capture             PostToolUse hook for Bash/Write/Edit/MultiEdit.
                      Read tool_name + tool_input + tool_response from
                      stdin. Append to a small rolling buffer. If this
                      call succeeded and a similar call recently failed,
                      promote the diff to a lesson.

  scan-subagent       SubagentStop hook.
                      Read transcript_path from stdin and scan the
                      JSONL transcript for retry-then-success patterns
                      that happened INSIDE the subagent (where our
                      PostToolUse hook never fires).

Design rules:
  - Project-scoped storage at .claude/lessons.json
  - Fail open. Hook crashes never block the parent flow.
  - Fast. PostToolUse fires constantly. Buffer is small, bounded.
  - Platform-aware JSON: matches Claude Code, Cursor, or Copilot CLI.
  - Structured lesson schema (v2). Auto-migrates v1 files on read.
"""
import json
import os
import sys
import re
import time
import platform
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

LESSONS_FILE = Path(".claude/lessons.json")
BUFFER_FILE = Path(".claude/.lesson-buffer.json")

# How far back to look in the buffer when matching a success against a
# prior failure. Keep this tight - 10 min and 30 calls - so unrelated
# events don't get spuriously paired.
BUFFER_MAX_ENTRIES = 30
BUFFER_MAX_AGE_SECONDS = 600

# Storage caps.
MAX_LESSONS_TOTAL = 40
MAX_CANDIDATES_TOTAL = 60
MAX_LESSONS_INJECTED = 12

# Promotion threshold: a lesson stays in candidate_lessons until it has
# been observed this many times across (potentially) different sessions.
# Real environment quirks repeat. TDD red-green coincidences don't.
PROMOTION_THRESHOLD = 3

# Markers that explicitly tell us a tool call's outcome should NOT be
# treated as a real failure-then-success pair. Skills that drive
# intentional failures (TDD red, debug repros, existence probes) prefix
# their bash `description` field with one of these. Case-insensitive.
INTENT_SKIP_MARKERS = (
    "[red]",          # TDD red phase - test should fail
    "[green]",        # TDD green phase - paired with [red]
    "[probe]",        # Exploratory check (does X exist?)
    "[verify]",       # Verifying a known state
    "[reproduce]",    # Deliberately reproducing a bug
    "[expected-fail]",  # Generic catch-all
)

SCHEMA_VERSION = 2


# ---------- platform / host detection ----------

def detect_environment() -> str:
    sysname = platform.system().lower()
    if sysname == "windows":
        return "windows"
    if sysname == "darwin":
        return "macos"
    if "microsoft" in platform.release().lower():
        return "wsl"
    return "linux"


def emit_for_host(event_name: str,
                  additional_context: str,
                  updated_input: Optional[Dict[str, Any]] = None,
                  permission_decision: Optional[str] = None) -> None:
    """Emit hook output JSON in the shape the current host expects."""
    in_cursor = bool(os.environ.get("CURSOR_PLUGIN_ROOT"))
    in_copilot = bool(os.environ.get("COPILOT_CLI"))
    in_claude = bool(os.environ.get("CLAUDE_PLUGIN_ROOT")) and not in_copilot

    if in_cursor:
        print(json.dumps({"additional_context": additional_context}))
        return

    if in_claude:
        hook_specific: Dict[str, Any] = {
            "hookEventName": event_name,
            "additionalContext": additional_context,
        }
        if permission_decision:
            hook_specific["permissionDecision"] = permission_decision
        if updated_input is not None:
            hook_specific["updatedInput"] = updated_input
        print(json.dumps({"hookSpecificOutput": hook_specific}))
        return

    print(json.dumps({"additionalContext": additional_context}))


# ---------- lessons storage ----------

def _default_lessons_doc() -> Dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "environment": detect_environment(),
        "last_updated": datetime.now().isoformat(),
        "global_constraints": [],
        "learned_lessons": [],
        "candidate_lessons": [],
    }


def _migrate_v1(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Promote a v1 doc (learned_rules) to v2 (learned_lessons)."""
    new_doc = _default_lessons_doc()
    new_doc["environment"] = doc.get("environment", new_doc["environment"])
    new_doc["global_constraints"] = doc.get("global_constraints", [])
    for r in doc.get("learned_rules", []):
        new_doc["learned_lessons"].append({
            "id": _make_lesson_id(r.get("pattern", ""), r.get("lesson", "")),
            "tool": "unknown",
            "summary": r.get("lesson", ""),
            "what_failed": r.get("pattern", ""),
            "what_worked": "",
            "source": "migrated-from-v1",
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "times_seen": int(r.get("retry_count", 1)),
        })
    return new_doc


def load_lessons() -> Dict[str, Any]:
    if not LESSONS_FILE.exists():
        return _default_lessons_doc()
    try:
        doc = json.loads(LESSONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _default_lessons_doc()
    if doc.get("version") != SCHEMA_VERSION:
        doc = _migrate_v1(doc)
    # Backfill new fields on docs written by an older v2 build.
    doc.setdefault("candidate_lessons", [])
    doc.setdefault("learned_lessons", [])
    doc.setdefault("global_constraints", [])
    return doc


def save_lessons(doc: Dict[str, Any]) -> None:
    LESSONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    doc["last_updated"] = datetime.now().isoformat()
    if len(doc.get("learned_lessons", [])) > MAX_LESSONS_TOTAL:
        # Sort by times_seen desc, then last_seen desc; keep the cap.
        doc["learned_lessons"].sort(
            key=lambda l: (l.get("times_seen", 1), l.get("last_seen", "")),
            reverse=True,
        )
        doc["learned_lessons"] = doc["learned_lessons"][:MAX_LESSONS_TOTAL]
    if len(doc.get("candidate_lessons", [])) > MAX_CANDIDATES_TOTAL:
        # Candidates rotate FIFO - if it didn't corroborate fast, drop it.
        doc["candidate_lessons"] = doc["candidate_lessons"][-MAX_CANDIDATES_TOTAL:]
    LESSONS_FILE.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _make_lesson_id(failed: str, worked: str) -> str:
    h = hashlib.sha1(f"{failed}||{worked}".encode("utf-8", errors="replace"))
    return h.hexdigest()[:10]


def _has_skip_marker(tool_input: Dict[str, Any]) -> bool:
    """
    True if this tool call's description carries an explicit intent
    marker telling us not to treat its outcome as a real failure.
    """
    if not isinstance(tool_input, dict):
        return False
    desc = tool_input.get("description", "")
    if not isinstance(desc, str):
        return False
    low = desc.lower().strip()
    return any(low.startswith(m) for m in INTENT_SKIP_MARKERS)


# ---------- buffer (recent tool calls) ----------

def load_buffer() -> List[Dict[str, Any]]:
    if not BUFFER_FILE.exists():
        return []
    try:
        return json.loads(BUFFER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_buffer(entries: List[Dict[str, Any]]) -> None:
    BUFFER_FILE.parent.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - BUFFER_MAX_AGE_SECONDS
    entries = [e for e in entries if e.get("ts", 0) >= cutoff]
    if len(entries) > BUFFER_MAX_ENTRIES:
        entries = entries[-BUFFER_MAX_ENTRIES:]
    BUFFER_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


# ---------- failure detection ----------

def is_failure(tool_name: str, tool_response: Any) -> Tuple[bool, str]:
    """
    Return (failed, error_excerpt) for a tool response.
    Conservative: only flag clear failure signals, never guess.
    The excerpt is the meaningful error text, not a stringified dict.
    """
    if isinstance(tool_response, dict):
        # Pull the most useful error string available, in priority order.
        def _err_text() -> str:
            for key in ("stderr", "error", "message", "stdout"):
                v = tool_response.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return _stringify(tool_response)

        if tool_response.get("is_error") is True:
            return True, _err_text()[:300]
        # Bash often surfaces non-zero exit via stderr without is_error.
        if tool_name == "Bash":
            stderr = tool_response.get("stderr", "") or ""
            stdout = tool_response.get("stdout", "") or ""
            combined = f"{stdout}\n{stderr}".lower()
            error_markers = (
                "command not found", "is not recognized", "permission denied",
                "no such file", "cannot find", "fatal:", "syntaxerror",
                "modulenotfounderror", "importerror", "error:",
                "traceback (most recent call last)",
            )
            if any(m in combined for m in error_markers):
                return True, (stderr or stdout).strip()[:300]
        return False, ""
    if isinstance(tool_response, str):
        low = tool_response.lower()
        if low.startswith("error") or "<tool_use_error>" in low:
            return True, tool_response.strip()[:300]
    return False, ""


def _stringify(x: Any) -> str:
    if isinstance(x, str):
        return x
    try:
        return json.dumps(x)[:500]
    except Exception:
        return str(x)[:500]


# ---------- retry / similarity matching ----------

def _bash_first_token(cmd: str) -> str:
    """Get the first non-flag token from a bash command."""
    if not isinstance(cmd, str):
        return ""
    for tok in cmd.strip().split():
        if not tok.startswith("-"):
            return tok.split("/")[-1].split("\\")[-1]  # strip path prefix
    return ""


def _bash_body(cmd: str) -> str:
    """Everything after the first non-flag token, normalized."""
    if not isinstance(cmd, str):
        return ""
    toks = cmd.strip().split()
    if not toks:
        return ""
    # Drop the first non-flag token; keep flags and remaining args.
    out: List[str] = []
    skipped_first = False
    for t in toks:
        if not skipped_first and not t.startswith("-"):
            skipped_first = True
            continue
        out.append(t)
    return " ".join(out)


def _input_signatures(tool_name: str, tool_input: Dict[str, Any]) -> List[str]:
    """
    Return one or more signatures used to pair a success with a recent
    failure. Multiple signatures = multiple ways the same call might be
    a retry of an earlier one (different command entirely vs. same
    command with a flag tweak).
    """
    if not isinstance(tool_input, dict):
        return []
    if tool_name == "Bash":
        cmd = tool_input.get("command", "") or ""
        first = _bash_first_token(cmd)
        body = _bash_body(cmd)
        sigs: List[str] = []
        if first:
            sigs.append(f"bash:first:{first}")
        if body:
            # Body match catches `python foo.py` -> `py foo.py` retries
            # where the interpreter swap is the whole point.
            sigs.append(f"bash:body:{body}")
        return sigs
    if tool_name in ("Write", "Edit", "MultiEdit"):
        return [f"{tool_name.lower()}::{tool_input.get('file_path', '')}"]
    return [f"{tool_name.lower()}::{json.dumps(tool_input, sort_keys=True)[:80]}"]


def _input_signature(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """First-choice signature for a tool input. Kept for back-compat."""
    sigs = _input_signatures(tool_name, tool_input)
    return sigs[0] if sigs else ""


def _input_summary(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Human-readable short version of an input."""
    if not isinstance(tool_input, dict):
        return ""
    if tool_name == "Bash":
        return (tool_input.get("command", "") or "").strip()[:200]
    if tool_name in ("Write", "Edit", "MultiEdit"):
        path = tool_input.get("file_path", "")
        old = tool_input.get("old_string", "")
        if old:
            return f"{path} (edit: {old[:60]}...)"
        return path
    return json.dumps(tool_input)[:200]


def find_matching_failure(
    tool_name: str, current_input: Dict[str, Any],
    buffer: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Look back through the buffer for a recent failure with any signature
    overlapping the current (successful) call's signatures. Body-match
    has higher specificity for command-swap retries (python -> py),
    while first-token match handles same-command-different-flag retries.
    """
    sigs = set(_input_signatures(tool_name, current_input))
    if not sigs:
        return None
    # Walk newest-to-oldest. Prefer body matches over first-token matches
    # (more specific - implies the rest of the command is identical).
    body_sigs = {s for s in sigs if s.startswith("bash:body:")}
    other_sigs = sigs - body_sigs

    def _check(entry_sigs_str: Any, against: set) -> bool:
        # entry["sigs"] is stored as list; older entries had "sig" str.
        if isinstance(entry_sigs_str, list):
            return any(s in against for s in entry_sigs_str)
        if isinstance(entry_sigs_str, str):
            return entry_sigs_str in against
        return False

    if body_sigs:
        for entry in reversed(buffer):
            if entry.get("tool") != tool_name or not entry.get("failed"):
                continue
            if entry.get("intentional"):
                continue
            if _check(entry.get("sigs") or entry.get("sig"), body_sigs):
                return entry
    for entry in reversed(buffer):
        if entry.get("tool") != tool_name or not entry.get("failed"):
            continue
        if entry.get("intentional"):
            continue
        if _check(entry.get("sigs") or entry.get("sig"), other_sigs):
            return entry
    return None


# ---------- lesson generation ----------

def build_lesson(tool_name: str,
                 failed_input: Dict[str, Any],
                 worked_input: Dict[str, Any],
                 error_excerpt: str,
                 source: str = "auto-postuse") -> Dict[str, Any]:
    failed_str = _input_summary(tool_name, failed_input)
    worked_str = _input_summary(tool_name, worked_input)
    summary = _natural_summary(tool_name, failed_str, worked_str, error_excerpt)
    return {
        "id": _make_lesson_id(failed_str, worked_str),
        "tool": tool_name,
        "summary": summary,
        "what_failed": failed_str,
        "what_worked": worked_str,
        "error_excerpt": error_excerpt[:200],
        "source": source,
        "first_seen": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
        "times_seen": 1,
    }


def _natural_summary(tool_name: str, failed: str, worked: str, err: str) -> str:
    if tool_name == "Bash":
        return (
            f"When using Bash here: `{failed}` failed"
            + (f" ({_first_line(err)})" if err else "")
            + f" — but `{worked}` worked."
        )
    if tool_name in ("Write", "Edit", "MultiEdit"):
        return (
            f"When editing files here ({tool_name}): the call against "
            f"`{failed}` failed"
            + (f" ({_first_line(err)})" if err else "")
            + f" — `{worked}` worked. Mind the difference next time."
        )
    return f"{tool_name} retry pattern: `{failed}` -> `{worked}`."


def _first_line(s: str) -> str:
    if not s:
        return ""
    return s.strip().splitlines()[0][:120]


def add_or_update_lesson(doc: Dict[str, Any], lesson: Dict[str, Any]) -> str:
    """
    Add or update a lesson, applying the promotion-threshold workflow:

      - First sighting: lands in candidate_lessons (not injected).
      - Each subsequent sighting: bumps times_seen on the candidate.
      - When times_seen >= PROMOTION_THRESHOLD: promoted to
        learned_lessons (becomes eligible for injection).
      - If the same lesson is already promoted: just bump times_seen.

    Returns one of: "promoted", "candidate-bumped", "candidate-new",
    "promoted-bumped" - useful for the caller's stderr log.
    """
    lesson_id = lesson["id"]

    # Already promoted? Just bump.
    for existing in doc.setdefault("learned_lessons", []):
        if existing.get("id") == lesson_id:
            existing["times_seen"] = existing.get("times_seen", 1) + 1
            existing["last_seen"] = lesson["last_seen"]
            return "promoted-bumped"

    # Existing candidate? Bump and check for promotion.
    candidates = doc.setdefault("candidate_lessons", [])
    for cand in candidates:
        if cand.get("id") == lesson_id:
            cand["times_seen"] = cand.get("times_seen", 1) + 1
            cand["last_seen"] = lesson["last_seen"]
            if cand["times_seen"] >= PROMOTION_THRESHOLD:
                # Promote - move from candidates to learned.
                candidates.remove(cand)
                doc["learned_lessons"].append(cand)
                return "promoted"
            return "candidate-bumped"

    # Brand new pattern - lands in candidates only.
    candidates.append(lesson)
    return "candidate-new"


# ---------- inject formatting ----------

def format_inject_block(doc: Dict[str, Any]) -> str:
    constraints = doc.get("global_constraints", [])
    lessons = doc.get("learned_lessons", [])

    # Rank by confidence: times_seen desc, then recency.
    ranked = sorted(
        lessons,
        key=lambda l: (l.get("times_seen", 1), l.get("last_seen", "")),
        reverse=True,
    )[:MAX_LESSONS_INJECTED]

    lines = [
        "=== PROJECT LESSONS (auto-learned from prior tool retries) ===",
        f"Environment: {doc.get('environment', 'unknown')}",
    ]
    if constraints:
        lines.append("Hard constraints for this project:")
        for c in constraints:
            lines.append(f"  - {c}")
    if ranked:
        lines.append("Lessons learned from prior runs in this project:")
        for l in ranked:
            seen = l.get("times_seen", 1)
            tag = f" (seen {seen}x)" if seen > 1 else ""
            lines.append(f"  - {l.get('summary', '')}{tag}")
    else:
        lines.append("(no auto-learned lessons yet — they accumulate as you work)")
    lines.append(
        "Apply these by default. They were learned from real failures in "
        "this exact project, not generic advice."
    )
    lines.append("=== END PROJECT LESSONS ===")
    return "\n".join(lines)


# ---------- transcript scanning ----------

def scan_transcript_for_retries(path: str) -> List[Dict[str, Any]]:
    """
    Walk a Claude Code JSONL transcript, pair tool failures with the next
    same-signature success from the same tool, and return new lessons.
    """
    try:
        p = Path(path)
        if not p.exists():
            return []
        recent_failures: List[Dict[str, Any]] = []  # like the live buffer
        new_lessons: List[Dict[str, Any]] = []
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                for call in _extract_tool_calls_from_jsonl_entry(obj):
                    tool = call["tool"]
                    inp = call["input"]
                    resp = call.get("response")
                    if resp is None:
                        # tool_use without paired tool_result yet; record
                        # provisionally so we can match the result later.
                        continue
                    failed, err = is_failure(tool, resp)
                    sigs = _input_signatures(tool, inp)
                    if not sigs:
                        continue
                    intentional = _has_skip_marker(inp)
                    if failed:
                        if intentional:
                            # Record but flag - never matchable. We keep
                            # it in the local list so the next-up search
                            # won't accidentally walk past it to an
                            # older real failure.
                            recent_failures.append({
                                "tool": tool, "sigs": sigs, "input": inp,
                                "error": err, "intentional": True,
                            })
                        else:
                            recent_failures.append({
                                "tool": tool, "sigs": sigs, "input": inp,
                                "error": err, "intentional": False,
                            })
                        if len(recent_failures) > BUFFER_MAX_ENTRIES:
                            recent_failures = recent_failures[-BUFFER_MAX_ENTRIES:]
                    else:
                        if intentional:
                            # A success marked [green] etc. is the paired
                            # half of an intentional failure - skip.
                            continue
                        # Success: prefer body-sig match over first-token.
                        body_sigs = {s for s in sigs if s.startswith("bash:body:")}
                        other_sigs = set(sigs) - body_sigs
                        match = None
                        for f_entry in reversed(recent_failures):
                            if f_entry["tool"] != tool:
                                continue
                            if f_entry.get("intentional"):
                                continue
                            f_sigs = set(f_entry["sigs"])
                            if body_sigs and (body_sigs & f_sigs):
                                match = f_entry
                                break
                        if match is None:
                            for f_entry in reversed(recent_failures):
                                if f_entry["tool"] != tool:
                                    continue
                                if f_entry.get("intentional"):
                                    continue
                                f_sigs = set(f_entry["sigs"])
                                if other_sigs & f_sigs:
                                    match = f_entry
                                    break
                        if match:
                            new_lessons.append(build_lesson(
                                tool, match["input"], inp,
                                match.get("error", ""),
                                source="auto-subagent-scan",
                            ))
                            recent_failures.remove(match)
        return new_lessons
    except Exception:
        return []


def _extract_tool_calls_from_jsonl_entry(obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Pull (tool, input, response) tuples from a single JSONL transcript line.
    Tolerant of schema variation across Claude Code versions.
    """
    out: List[Dict[str, Any]] = []
    msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_use":
                out.append({
                    "tool": block.get("name", ""),
                    "input": block.get("input", {}) or {},
                    "response": None,
                })
            elif btype == "tool_result":
                # tool_result usually appears in a separate message after
                # tool_use. We can't perfectly pair here without ID
                # tracking; fold the result into the most recent open
                # tool_use we've emitted.
                resp = block.get("content")
                # Some hosts surface is_error at this level
                if isinstance(resp, list):
                    parts = []
                    for c in resp:
                        if isinstance(c, dict) and "text" in c:
                            parts.append(c["text"])
                    resp = "\n".join(parts) if parts else resp
                out.append({
                    "tool": "_result_",
                    "input": {},
                    "response": resp,
                    "is_error": block.get("is_error", False),
                })
    # If toolUseResult is at the top level (some Claude Code versions)
    if "toolUseResult" in obj:
        out.append({
            "tool": "_result_",
            "input": {},
            "response": obj["toolUseResult"],
        })
    # Pair _result_ entries back into the most recent same-position
    # tool_use. Simplification: walk pairs in order.
    paired: List[Dict[str, Any]] = []
    pending: Optional[Dict[str, Any]] = None
    for c in out:
        if c["tool"] == "_result_":
            if pending is not None:
                pending["response"] = c.get("response")
                if c.get("is_error"):
                    if isinstance(pending["response"], dict):
                        pending["response"]["is_error"] = True
                    else:
                        pending["response"] = {
                            "is_error": True,
                            "stderr": _stringify(pending["response"]),
                        }
                paired.append(pending)
                pending = None
        else:
            if pending is not None:
                paired.append(pending)
            pending = c
    if pending is not None and pending["tool"] != "_result_":
        paired.append(pending)
    return [p for p in paired if p["tool"] not in ("", "_result_")]


# ---------- mode handlers ----------

def cmd_inject() -> int:
    doc = load_lessons()
    block = format_inject_block(doc)
    emit_for_host("SessionStart", block)
    return 0


def cmd_inject_subagent() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    doc = load_lessons()
    block = format_inject_block(doc)
    tool_input = payload.get("tool_input") or {}
    original_prompt = tool_input.get("prompt", "")
    new_prompt = f"{block}\n\n---\n\n{original_prompt}" if original_prompt else block
    updated_input = {**tool_input, "prompt": new_prompt}
    emit_for_host(
        "PreToolUse", block,
        updated_input=updated_input,
        permission_decision="allow",
    )
    return 0


def cmd_capture() -> int:
    """PostToolUse: log call; pair successes with prior similar failures."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    tool_response = payload.get("tool_response")

    # Only pay attention to tools we know how to summarize meaningfully.
    if tool_name not in ("Bash", "Write", "Edit", "MultiEdit"):
        return 0

    failed, err = is_failure(tool_name, tool_response)
    sigs = _input_signatures(tool_name, tool_input)
    if not sigs:
        return 0

    # Skill-side intent declaration: if the description starts with a
    # known marker (e.g., [red] for TDD), the failure is intentional and
    # must not be paired with a subsequent success. We still record it
    # in the buffer (debugging visibility) but flag it as intentional.
    intentional = _has_skip_marker(tool_input)

    buffer = load_buffer()
    entry = {
        "ts": time.time(),
        "tool": tool_name,
        "sigs": sigs,
        "input": tool_input,
        "failed": failed,
        "intentional": intentional,
        "error": err if failed else "",
    }

    if not failed and not intentional:
        match = find_matching_failure(tool_name, tool_input, buffer)
        if match is not None:
            doc = load_lessons()
            lesson = build_lesson(
                tool_name, match["input"], tool_input,
                match.get("error", ""),
                source="auto-postuse",
            )
            outcome = add_or_update_lesson(doc, lesson)
            save_lessons(doc)
            match_ts = match.get("ts")
            buffer = [b for b in buffer if b.get("ts") != match_ts]
            sys.stderr.write(
                f"[lesson-tracker] {outcome}: {lesson['summary'][:120]}\n"
            )

    buffer.append(entry)
    save_buffer(buffer)
    return 0


def cmd_scan_subagent() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    transcript_path = payload.get("transcript_path") or payload.get("transcriptPath")
    if not transcript_path:
        return 0
    new_lessons = scan_transcript_for_retries(transcript_path)
    if not new_lessons:
        return 0
    doc = load_lessons()
    promoted = 0
    candidate = 0
    for nl in new_lessons:
        outcome = add_or_update_lesson(doc, nl)
        if outcome.startswith("promoted"):
            promoted += 1
        else:
            candidate += 1
    save_lessons(doc)
    sys.stderr.write(
        f"[lesson-tracker] subagent scan: {promoted} promoted, {candidate} candidate\n"
    )
    return 0


# ---------- entrypoint ----------

def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "inject"
    try:
        if action == "inject":
            return cmd_inject()
        if action == "inject-subagent":
            return cmd_inject_subagent()
        if action == "capture":
            return cmd_capture()
        if action == "scan-subagent":
            return cmd_scan_subagent()
        sys.stderr.write(f"[lesson-tracker] unknown action: {action}\n")
        return 0
    except Exception as e:
        sys.stderr.write(f"[lesson-tracker] error: {e}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
