# Offload Task Prompt Template

This file is the production template used by `build_prompt()` in `offload/prompt.py`.
It contains exactly four placeholders that are filled at runtime:

- `{target_path}` — the file(s) to create or modify (comma-separated paths)
- `{spec}` — the task specification describing what to implement
- `{acceptance_criteria}` — bullet list of acceptance criteria the output must satisfy
- `{verify_command}` — shell command that exits 0 when the task is complete

---

You are implementing a coding task. Read the requirements carefully.

**Target file(s):** {target_path}

**Specification:**
{spec}

**Acceptance criteria (ALL must pass):**
{acceptance_criteria}

**Verification command:** `{verify_command}`

---

## Output format

Return the complete file(s) as the JSON envelope shown below.
Do NOT use diffs, patches, search/replace blocks, or markdown fences.
Do NOT elide any part of any file (no `# ... rest unchanged ...` or similar).
Every file listed in `files` must contain its COMPLETE contents from the first
line to the last — nothing omitted.

```json
{
  "confidence": "high" | "medium" | "low",
  "files": [
    {
      "path": "relative/path/to/file.py",
      "content": "<entire file contents as a single string>"
    }
  ],
  "notes": "<optional: any clarification or caveat>"
}
```

If you are not confident you can produce a correct, complete implementation,
set `confidence` to `"low"` rather than guessing or producing partial output.
