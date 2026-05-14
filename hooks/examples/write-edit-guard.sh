#!/usr/bin/env bash
# PostToolUse hook: warn when a Write/Edit produces suspiciously small output
# or touches a sensitive config file. Designed for use with continueOnBlock: true.
#
# Opt in via .claude/settings.local.json:
#
#   "PostToolUse": [{
#     "matcher": "Write|Edit",
#     "hooks": [{
#       "type": "command",
#       "continueOnBlock": true,
#       "args": ["/bin/bash", "${CLAUDE_PLUGIN_ROOT}/hooks/examples/write-edit-guard.sh"]
#     }]
#   }]
#
# With continueOnBlock: true the exit-2 message is fed back to Claude as
# context and the turn continues — Claude can then decide whether to restore
# the file or confirm the change was intentional.
#
# Fail-open: any parse error exits 0 so this hook never blocks the session.

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
[[ -z "$TOOL_NAME" ]] && exit 0
[[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]] && exit 0

FILE_PATH=$(echo "$INPUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null || echo "")
[[ -z "$FILE_PATH" ]] && exit 0

# Sensitive file check — matches .env*, settings.json, *.yaml, *.toml, *.cfg at any depth
BASENAME=$(basename "$FILE_PATH")
if echo "$BASENAME" | grep -qE '^\.env|^settings\.json$|\.ya?ml$|\.toml$|\.cfg$'; then
    echo "file-guard: '${BASENAME}' is a recognized config file. Verify this change is intentional before continuing." >&2
    exit 2
fi

# Size collapse check
if [[ "$TOOL_NAME" == "Write" ]]; then
    LINE_COUNT=$(echo "$INPUT" | "$PY" -c \
      "import json,sys; d=json.load(sys.stdin); c=d.get('tool_input',{}).get('content',''); print(len(c.splitlines()))" \
      2>/dev/null || echo "0")
    if [[ "${LINE_COUNT:-0}" -lt 20 && "${LINE_COUNT:-0}" -gt 0 ]]; then
        echo "file-guard: '${BASENAME}' was written with only ${LINE_COUNT} lines. If this replaced a larger file, verify it was intentional." >&2
        exit 2
    fi
fi

if [[ "$TOOL_NAME" == "Edit" ]]; then
    OLD_LINES=$(echo "$INPUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('tool_input',{}).get('old_string','').splitlines()))" 2>/dev/null || echo "0")
    NEW_LINES=$(echo "$INPUT" | "$PY" -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('tool_input',{}).get('new_string','').splitlines()))" 2>/dev/null || echo "0")
    if [[ "${OLD_LINES:-0}" -gt 0 && "${NEW_LINES:-0}" -gt 0 ]]; then
        RATIO=$(( OLD_LINES * 10 / NEW_LINES ))
        if [[ "$RATIO" -ge 30 ]]; then
            echo "file-guard: Edit in '${BASENAME}' removed ~$((OLD_LINES - NEW_LINES)) lines (${OLD_LINES} → ${NEW_LINES}). Verify this contraction was intentional." >&2
            exit 2
        fi
    fi
fi

exit 0
