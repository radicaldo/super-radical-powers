"""
prompt.py — Turn a task dict into system+user prompts for the local Ollama model.

Key design constraint: local models fail at diff/patch edits and elide code
("# ... rest unchanged ..."). The prompt MUST force complete file contents as
a JSON envelope — never diffs, never elisions, never markdown fences.
"""

SYSTEM_PROMPT = (
    "You generate COMPLETE source files. Output ONLY the JSON object matching the schema. "
    "Each files[].content MUST be the entire file from first line to last. "
    "NEVER output diffs, patches, search/replace blocks, '# ... existing code ...' elisions, "
    "or markdown code fences. If you cannot produce a complete correct file, set confidence='low'."
)


def build_prompt(task: dict, template: str) -> str:
    """Render `template` with values from `task`.

    Supported placeholders:
        {target_path}        — task['target_files'] joined by ', '
        {spec}               — task['spec']
        {acceptance_criteria} — task.get('acceptance_criteria', []) as '- item' lines
        {verify_command}     — task['verify_command']

    Uses explicit str.replace so that incidental braces in spec/content never
    raise KeyError or IndexError. Any unsupported {placeholder} tokens are left
    in place (callers should not use our 4 reserved names for other purposes).
    """
    target_path = ", ".join(task.get("target_files") or [])
    spec = task.get("spec", "")
    criteria_lines = "\n".join(
        f"- {item}" for item in (task.get("acceptance_criteria") or [])
    )
    verify_command = task.get("verify_command", "")

    result = template
    result = result.replace("{target_path}", target_path)
    result = result.replace("{spec}", spec)
    result = result.replace("{acceptance_criteria}", criteria_lines)
    result = result.replace("{verify_command}", verify_command)
    return result
