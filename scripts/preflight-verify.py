#!/usr/bin/env python3
"""
preflight-verify.py — Flight check for super-radical-powers

Modes:
  verify         Run check_cmds filtered by blast_radius, update last_verified_at.
  inject         Emit flight-check environment + project as additionalContext for SessionStart.
  inject-subagent Prepend assertions block to a Task subagent's prompt via updatedInput.
  handoff-parse  Extract assertions_checked from a subagent transcript (SubagentStop fallback).
  init           Scaffold a new flight-check.yaml from the current environment.
  status         Print last verification results without re-running.

Usage (via run-hook.cmd):
  preflight-verify verify [--radius global|project|hooks|all] [--strict]
  preflight-verify inject
  preflight-verify inject-subagent
  preflight-verify handoff-parse
  preflight-verify init
  preflight-verify status

Exit codes:
  0  All critical assertions passed (or mode doesn't check assertions)
  1  One or more critical assertions failed (--strict: any failure)
  2  flight-check.yaml not found or malformed
"""

import sys
import os
import json
import re
import subprocess
import argparse
import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    # Inline minimal YAML loader for simple key:value + lists (no deps required)
    yaml = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FLIGHT_CHECK_FILENAME = "flight-check.yaml"
HANDOFFS_DIR = "handoffs"

# Path resolution: same pattern as lesson-tracker.py.
# Claude Code sets cwd to the user's project directory during hook
# execution. CLAUDE_PROJECT_DIR is the explicit env var; cwd is the
# fallback. The flight-check.yaml and handoffs/ live in the USER's
# project .claude/ directory, NOT in the plugin directory.
FLIGHT_CHECK_FILE = Path(".claude") / FLIGHT_CHECK_FILENAME
HANDOFFS_PATH = Path(".claude") / HANDOFFS_DIR


def get_project_dir() -> Path:
    """Return the user's project directory (not the plugin directory).

    During hook execution, Claude Code sets both CLAUDE_PROJECT_DIR and
    cwd to the user's project. During slash-command invocation, Claude
    runs bash in the project dir. Either way, the result is the same.
    """
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())).resolve()


def flight_check_path() -> Path:
    return get_project_dir() / FLIGHT_CHECK_FILE


def handoffs_path() -> Path:
    return get_project_dir() / HANDOFFS_PATH


def load_yaml(path: Path) -> dict:
    """Load YAML, falling back to json if yaml module unavailable."""
    text = path.read_text(encoding="utf-8")
    if yaml:
        return yaml.safe_load(text)
    # Minimal fallback: try JSON (won't work for real YAML but avoids hard crash)
    try:
        return json.loads(text)
    except Exception:
        die(f"yaml module not installed and {path} is not valid JSON. "
            "Run: pip install pyyaml --break-system-packages", 2)


def dump_yaml(data: dict, path: Path):
    if yaml:
        path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False),
                        encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def die(msg: str, code: int = 2):
    print(f"[preflight] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def log(msg: str):
    print(f"[preflight] {msg}", file=sys.stderr)


def now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Core: run a single assertion's check_cmd
# ---------------------------------------------------------------------------

def run_assertion(assertion: dict) -> dict:
    """
    Run check_cmd, match expected_pattern against stdout+stderr.
    Returns enriched dict with: passed, exit_code, output_snippet, duration_ms.
    """
    cmd = assertion.get("check_cmd", "")
    pattern = assertion.get("expected_pattern", ".")
    result = {
        "id": assertion["id"],
        "passed": False,
        "exit_code": -1,
        "output_snippet": "",
        "duration_ms": 0,
    }
    if not cmd:
        result["output_snippet"] = "no check_cmd defined"
        return result

    t_start = datetime.datetime.utcnow()
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()),
        )
        combined = (proc.stdout + proc.stderr).strip()
        result["exit_code"] = proc.returncode
        result["output_snippet"] = combined[:200]
        # Match pattern: "." means any non-empty output
        if pattern == ".":
            result["passed"] = bool(combined)
        else:
            result["passed"] = bool(re.search(pattern, combined, re.IGNORECASE))
    except subprocess.TimeoutExpired:
        result["output_snippet"] = "timeout after 30s"
    except Exception as exc:
        result["output_snippet"] = str(exc)[:200]

    elapsed = (datetime.datetime.utcnow() - t_start).total_seconds()
    result["duration_ms"] = int(elapsed * 1000)
    return result


# ---------------------------------------------------------------------------
# Mode: verify
# ---------------------------------------------------------------------------

def mode_verify(fc: dict, radius: str, strict: bool) -> int:
    assertions = fc.get("assertions", [])
    if not assertions:
        log("No assertions defined in flight-check.yaml")
        return 0

    radius_filter = {"global", "project", "hooks"} if radius == "all" else {radius}
    targets = [a for a in assertions if a.get("blast_radius", "project") in radius_filter]

    if not targets:
        log(f"No assertions match blast_radius={radius}")
        return 0

    results = []
    critical_failures = []
    any_failures = []

    for assertion in targets:
        r = run_assertion(assertion)
        results.append(r)
        status = "PASS" if r["passed"] else "FAIL"
        crit = " [critical]" if assertion.get("critical") else ""
        log(f"  {status}  {assertion['id']} — {assertion.get('description','')}{crit} "
            f"({r['duration_ms']}ms)")
        if not r["passed"]:
            any_failures.append(assertion["id"])
            if assertion.get("critical"):
                critical_failures.append(assertion["id"])

    # Update last_verified_at in file
    fc_path = flight_check_path()
    fc.setdefault("meta", {})["last_verified_at"] = now_iso()
    # Store last results summary alongside meta
    fc["meta"]["last_results"] = {
        "ran": [r["id"] for r in results],
        "passed": [r["id"] for r in results if r["passed"]],
        "failed": any_failures,
        "critical_failed": critical_failures,
    }
    dump_yaml(fc, fc_path)

    if critical_failures:
        log(f"BLOCKED — critical failures: {', '.join(critical_failures)}")
        return 1
    if strict and any_failures:
        log(f"BLOCKED (strict) — failures: {', '.join(any_failures)}")
        return 1

    log("Flight check passed.")
    return 0


# ---------------------------------------------------------------------------
# Mode: inject (SessionStart → additionalContext)
# ---------------------------------------------------------------------------

def mode_inject(fc: dict):
    env = fc.get("environment", {})
    proj = fc.get("project", {})
    runtimes = fc.get("runtimes", [])
    meta = fc.get("meta", {})

    lines = [
        "## Flight Check — Environment",
        f"- host_os: {env.get('host_os', 'unknown')}",
        f"- shell_primary: {env.get('shell_primary', 'unknown')}",
        f"- shells_available: {', '.join(env.get('shells_available', []))}",
        f"- container_runtime: {env.get('container_runtime', 'none')}",
        f"- container_compose: {env.get('container_compose', False)}",
    ]
    if env.get("notes"):
        lines.append(f"- notes: {env['notes']}")

    lines.append("\n## Runtimes")
    for rt in runtimes:
        lines.append(f"- {rt['id']}: path={rt.get('path', 'on PATH')}, "
                     f"check=`{rt.get('check_cmd','')}`, "
                     f"critical={rt.get('critical', False)}")

    lines.append("\n## Project")
    lines += [
        f"- root: {proj.get('root', 'cwd')}",
        f"- test_cmd: {proj.get('test_cmd', '')}",
        f"- lint_cmd: {proj.get('lint_cmd', '')}",
        f"- test_paths: {', '.join(proj.get('test_paths', []))}",
    ]
    if proj.get("notes"):
        lines.append(f"- notes: {proj['notes']}")

    last_verified = meta.get("last_verified_at", "never")
    lines.append(f"\n_Flight check last verified: {last_verified}_")

    context = "\n".join(lines)
    output = {"hookSpecificOutput": {"additionalContext": context}}
    print(json.dumps(output))


# ---------------------------------------------------------------------------
# Mode: inject-subagent (PreToolUse Task → updatedInput)
# ---------------------------------------------------------------------------

def mode_inject_subagent(fc: dict):
    """
    Read Task tool input from stdin (Claude Code hook format),
    prepend assertions block to the subagent prompt.
    """
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        hook_input = {}

    assertions = fc.get("assertions", [])
    if not assertions:
        print(json.dumps({}))
        return

    lines = ["## Preflight Assertions — your responsibility this feature", ""]
    for a in assertions:
        crit = " [CRITICAL]" if a.get("critical") else ""
        lines.append(f"- {a['id']}{crit}: {a.get('description','')}")
        lines.append(f"  verify with: `{a.get('check_cmd','')}`")
        lines.append(f"  expected: `{a.get('expected_pattern','')}`")
        lines.append("")
    lines.append("Write your assertions_checked results in the handoff YAML "
                 "at .claude/handoffs/ when you finish.\n")

    assertions_block = "\n".join(lines)

    # Patch the Task tool's prompt field. Claude Code's PreToolUse
    # contract expects updatedInput to be the new tool_input, nested
    # inside hookSpecificOutput - not the entire hook payload at the
    # top level. Match lesson-tracker.cmd_inject_subagent's shape.
    task_input = hook_input.get("tool_input", {}) or {}
    existing_prompt = task_input.get("prompt", "")
    new_prompt = (
        f"{assertions_block}\n\n---\n\n{existing_prompt}"
        if existing_prompt else assertions_block
    )
    updated_input = {**task_input, "prompt": new_prompt}

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": assertions_block,
            "updatedInput": updated_input,
        }
    }
    print(json.dumps(output))


# ---------------------------------------------------------------------------
# Mode: handoff-parse (SubagentStop fallback)
# ---------------------------------------------------------------------------

def mode_handoff_parse():
    """
    Read SubagentStop hook JSON from stdin (contains transcript_path).
    If no handoff file was written by the subagent, attempt to extract
    assertions_checked from the transcript JSONL and write a minimal handoff.
    """
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        hook_input = {}

    transcript_path = hook_input.get("transcript_path", "")
    session_id = hook_input.get("session_id", "unknown")

    if not transcript_path or not Path(transcript_path).exists():
        log("No transcript_path in SubagentStop input — skipping handoff-parse")
        print(json.dumps({}))
        return

    handoffs_dir = handoffs_path()
    handoffs_dir.mkdir(parents=True, exist_ok=True)

    # Check if a handoff was already written this session
    existing = list(handoffs_dir.glob(f"handoff-*-{session_id[:8]}*.yaml"))
    if existing:
        log(f"Handoff already written for session {session_id[:8]} — skipping parse")
        print(json.dumps({}))
        return

    # Minimal extraction: scan transcript for assertion IDs and pass/fail signals
    transcript = Path(transcript_path).read_text(encoding="utf-8", errors="replace")
    a_id_pattern = re.compile(r'\b(A-\d{3})\b')
    pass_pattern = re.compile(r'(passed|success|ok|0 failed)', re.IGNORECASE)
    fail_pattern = re.compile(r'(failed|error|exit code [^0])', re.IGNORECASE)

    found_ids = list(dict.fromkeys(a_id_pattern.findall(transcript)))
    checked = []
    for aid in found_ids:
        # Very rough heuristic: look for pass/fail near each assertion ID
        idx = transcript.rfind(aid)
        window = transcript[max(0, idx - 100):idx + 300]
        passed = bool(pass_pattern.search(window)) and not bool(fail_pattern.search(window))
        checked.append({"id": aid, "passed": passed,
                        "exit_code": 0 if passed else 1,
                        "output_snippet": "(extracted from transcript)"})

    if not checked:
        log("No assertion IDs found in transcript — no handoff written")
        print(json.dumps({}))
        return

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    handoff = {
        "summary": "(Auto-generated from transcript — worker did not write a handoff)",
        "feature_id": f"auto-{session_id[:8]}",
        "worker_session": session_id,
        "assertions_assigned": found_ids,
        "assertions_checked": checked,
        "commands_run": [],
        "left_undone": "",
        "issues_discovered": "",
        "procedures_followed": False,
        "_auto_generated": True,
    }

    out_path = handoffs_dir / f"handoff-auto-{session_id[:8]}-{timestamp}.yaml"
    dump_yaml(handoff, out_path)
    log(f"Auto-handoff written to {out_path.name}")
    print(json.dumps({}))


# ---------------------------------------------------------------------------
# Mode: init
# ---------------------------------------------------------------------------

def mode_init():
    project_root = get_project_dir()
    fc_path = flight_check_path()
    if fc_path.exists():
        log(f"flight-check.yaml already exists at {fc_path} — not overwriting. "
            "Delete it first if you want to re-scaffold.")
        sys.exit(0)

    # Probe environment
    def probe(cmd):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            return r.stdout.strip() or r.stderr.strip()
        except Exception:
            return ""

    python_path = probe("python -c \"import sys; print(sys.executable)\"")
    python_ver = probe("python --version")
    node_ver = probe("node --version")
    docker_ver = probe("docker --version")
    wsl_ok = probe("wsl echo ok").strip() == "ok"

    # Detect shell
    shell = "powershell" if os.name == "nt" else "bash"
    shells = ["powershell", "cmd"]
    if wsl_ok:
        shells.append("wsl-bash")

    scaffold = {
        "meta": {
            "schema_version": "1.0",
            "project": project_root.name,
            "generated_at": now_iso(),
            "last_verified_at": None,
            "verified_by": "preflight-verify.py",
        },
        "environment": {
            "host_os": "Windows 11" if os.name == "nt" else "Linux",
            "ide": "vscode",
            "shell_primary": shell,
            "shells_available": shells,
            "container_runtime": "docker" if docker_ver else "none",
            "container_compose": bool(docker_ver),
            "notes": "Auto-scaffolded — review and adjust.",
        },
        "runtimes": [],
        "project": {
            "root": str(project_root),
            "test_cmd": "uv run pytest",
            "lint_cmd": "ruff check .",
            "build_cmd": "",
            "test_paths": ["tests"],
            "notes": "",
        },
        "assertions": [
            {
                "id": "A-001",
                "description": "Correct Python interpreter resolves on PATH",
                "check_cmd": "python -c \"import sys; print(sys.executable)\"",
                "expected_pattern": python_path.split("\\")[-2] if python_path else "python",
                "critical": True,
                "blast_radius": "global",
            },
            {
                "id": "A-002",
                "description": "Project test suite passes baseline",
                "check_cmd": "uv run pytest --tb=no -q",
                "expected_pattern": "passed",
                "critical": True,
                "blast_radius": "project",
            },
        ],
    }

    if python_path:
        scaffold["runtimes"].append({
            "id": "python",
            "path": python_path,
            "check_cmd": "python --version",
            "expected_pattern": python_ver.split()[1][:4] if python_ver else "3.",
            "critical": True,
        })
    if node_ver:
        scaffold["runtimes"].append({
            "id": "node",
            "check_cmd": "node --version",
            "expected_pattern": node_ver[:3],
            "critical": False,
        })
    if docker_ver:
        scaffold["runtimes"].append({
            "id": "docker",
            "check_cmd": "docker info --format '{{.ServerVersion}}'",
            "expected_pattern": ".",
            "critical": False,
        })
        scaffold["assertions"].append({
            "id": "A-003",
            "description": "Docker daemon is reachable",
            "check_cmd": "docker ps",
            "expected_pattern": "CONTAINER",
            "critical": False,
            "blast_radius": "project",
        })
    if wsl_ok:
        scaffold["assertions"].append({
            "id": "A-004",
            "description": "WSL shell accessible for cross-platform hooks",
            "check_cmd": "wsl echo ok",
            "expected_pattern": "ok",
            "critical": False,
            "blast_radius": "hooks",
        })

    fc_path.parent.mkdir(parents=True, exist_ok=True)
    dump_yaml(scaffold, fc_path)
    log(f"Scaffolded {fc_path}")
    log("Review and adjust, then run: preflight-verify verify --radius all")


# ---------------------------------------------------------------------------
# Mode: status
# ---------------------------------------------------------------------------

def mode_status(fc: dict):
    meta = fc.get("meta", {})
    last = meta.get("last_verified_at", "never")
    results = meta.get("last_results", {})
    print(f"Last verified : {last}")
    if results:
        print(f"Passed        : {', '.join(results.get('passed', [])) or 'none'}")
        print(f"Failed        : {', '.join(results.get('failed', [])) or 'none'}")
        print(f"Critical fail : {', '.join(results.get('critical_failed', [])) or 'none'}")
    else:
        print("No previous results stored. Run: preflight-verify verify")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Preflight contract verifier for super-radical-powers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("mode", choices=[
        "verify", "inject", "inject-subagent", "handoff-parse", "init", "status"
    ])
    parser.add_argument("--radius", default="global",
                        choices=["global", "project", "hooks", "all"],
                        help="Filter assertions by blast_radius (verify mode)")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 on any failure, not just critical (verify mode)")
    args = parser.parse_args()

    # init and handoff-parse don't need an existing flight-check.yaml
    if args.mode == "init":
        mode_init()
        return
    if args.mode == "handoff-parse":
        mode_handoff_parse()
        return

    project_root = get_project_dir()
    fc_path = flight_check_path()

    if not fc_path.exists():
        if args.mode in ("inject", "inject-subagent"):
            # Fail open — don't block the session if no flight-check exists yet
            print(json.dumps({}))
            return
        die(f"flight-check.yaml not found at {fc_path}. "
            "Run: preflight-verify init", 2)

    fc = load_yaml(fc_path)

    if args.mode == "verify":
        sys.exit(mode_verify(fc, args.radius, args.strict))
    elif args.mode == "inject":
        mode_inject(fc)
    elif args.mode == "inject-subagent":
        mode_inject_subagent(fc)
    elif args.mode == "status":
        mode_status(fc)


if __name__ == "__main__":
    main()
