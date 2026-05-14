#!/usr/bin/env bash
# PostToolUse hook: scan Bash tool output for known error patterns and
# feed a contextual recovery hint back to Claude via continueOnBlock.
#
# Opt in via .claude/settings.local.json:
#
#   "PostToolUse": [{
#     "matcher": "Bash",
#     "hooks": [{
#       "type": "command",
#       "continueOnBlock": true,
#       "args": ["/bin/bash", "${CLAUDE_PLUGIN_ROOT}/hooks/examples/bash-output-sniffer.sh"]
#     }]
#   }]
#
# Fail-open: any parse/read error exits 0.
# Note: PostToolUse hooks receive tool INPUT via stdin, not tool output.
# Tool output must be read from the transcript JSONL file. This script
# walks the transcript in reverse to find the most recent Bash tool result.

trap 'exit 0' ERR
set -euo pipefail

# Resolve a working Python interpreter (python3 preferred; fall back to python)
PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo "")
if [[ -n "$PY" ]]; then
    # Verify the resolved interpreter is not a stub (e.g. Windows Store redirect)
    if ! echo "" | "$PY" -c "import sys; sys.exit(0)" 2>/dev/null; then
        PY=$(command -v python 2>/dev/null || echo "")
    fi
fi
[[ -z "$PY" ]] && exit 0

INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_name',''))" 2>/dev/null || echo "")
[[ "$TOOL_NAME" != "Bash" ]] && exit 0

TRANSCRIPT_PATH=$(echo "$INPUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); print(d.get('transcript_path',''))" 2>/dev/null || echo "")
[[ -z "$TRANSCRIPT_PATH" || ! -f "$TRANSCRIPT_PATH" ]] && exit 0

# Extract the last Bash tool result content from the transcript
LAST_OUTPUT=$("$PY" -c "
import json, sys
path = sys.argv[1]
output = ''
try:
    with open(path) as f:
        lines = f.readlines()
except Exception:
    sys.exit(0)

for line in reversed(lines):
    try:
        entry = json.loads(line)
    except Exception:
        continue
    if entry.get('type') not in ("tool", "tool_result"):
        continue
    content = entry.get('content', [])
    if isinstance(content, list):
        parts = [c.get('text', '') for c in content if isinstance(c, dict) and c.get('type') == 'text']
        if parts:
            print('\n'.join(parts))
            break
    elif isinstance(content, str):
        print(content)
        break
" "$TRANSCRIPT_PATH" 2>/dev/null || echo "")

[[ -z "$LAST_OUTPUT" ]] && exit 0

# Pattern -> hint mapping (checked in order; first match wins)
check_pattern() {
    local pattern="$1"
    local hint="$2"
    if echo "$LAST_OUTPUT" | grep -qiF "$pattern"; then
        echo "bash-sniffer: $hint" >&2
        exit 2
    fi
}

check_pattern "Permission denied"         "'Permission denied' in output -- check file ownership or consider sudo."
check_pattern "command not found"         "'command not found' -- verify the tool is installed and on PATH."
check_pattern "No such file or directory" "'No such file or directory' -- check the path exists before retrying."
check_pattern "ModuleNotFoundError"       "'ModuleNotFoundError' -- the Python package may not be installed in the active environment."
check_pattern "Cannot find module"        "'Cannot find module' -- run npm install or check the import path."
check_pattern "ENOENT"                    "'ENOENT' -- a required file or directory is missing."
check_pattern "Error: EPERM"              "'EPERM' -- operation not permitted; check permissions or run as administrator."

exit 0
