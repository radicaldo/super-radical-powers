#!/usr/bin/env python3
import json
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

LESSONS_FILE = Path(".claude/lessons.json")
MAX_RULES = 20

def load_lessons() -> Dict[str, Any]:
    if LESSONS_FILE.exists():
        try:
            return json.loads(LESSONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "environment": "windows-powershell",
        "last_updated": datetime.now().isoformat(),
        "learned_rules": [],
        "global_constraints": ["No sudo", "Use pwsh-compatible syntax", "Full Windows paths for volumes"]
    }

def save_lessons(data: Dict[str, Any]):
    LESSONS_FILE.parent.mkdir(exist_ok=True)
    data["last_updated"] = datetime.now().isoformat()
    LESSONS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def extract_retries_from_text(text: str) -> List[Dict[str, Any]]:
    lessons = []
    # Capture failure → retry → success patterns
    patterns = re.findall(r'(?i)(?:failed|error|exception|permission|not found).*?(?:retry|trying|retried|success|worked with|fixed by)(.*?)(?=\n\n|\Z)', text, re.DOTALL | re.IGNORECASE)
    
    for match in patterns[:6]:
        cmd_match = re.search(r'(`[^`]+`|\$\s*\w+|\& \w+|[a-zA-Z0-9_.-]+\s+[^\n]{10,40})', match)
        if cmd_match:
            cmd = cmd_match.group(1).strip('`')
            lessons.append({
                "pattern": cmd.split()[0] if ' ' in cmd else cmd,
                "lesson": f"Windows fix: {cmd}",
                "retry_count": 1,
                "first_success_task": "auto-detected"
            })
    
    # Docker / shell common Windows lessons
    if re.search(r'(?i)docker|bash|sh -c|sudo|volume', text):
        lessons.append({
            "pattern": "container commands",
            "lesson": "Always use & docker ... or pwsh array syntax. Never assume bash. Use full Windows paths or /c/ prefix for volumes.",
            "retry_count": 1,
            "first_success_task": "auto-detected"
        })
    
    return lessons

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "inject"
    lessons = load_lessons()
    
    if action == "inject":
        print("\n=== LESSON TRACKER: APPLYING LEARNED RULES ===")
        for rule in lessons.get("learned_rules", [])[-8:]:
            print(f" {rule['pattern']}: {rule['lesson']}")
        print("============================================\n")
        
        print("LESSONS_INJECTION_START")
        print(json.dumps(lessons, indent=2))
        print("LESSONS_INJECTION_END")
    
    elif action == "parse" and len(sys.argv) > 2:
        context = " ".join(sys.argv[2:])  # Handle quoted context
        new_lessons = extract_retries_from_text(context)
        
        for nl in new_lessons:
            # Deduplicate
            if not any(nl["pattern"].lower() in existing["pattern"].lower() for existing in lessons["learned_rules"]):
                lessons["learned_rules"].append(nl)
        
        if len(lessons["learned_rules"]) > MAX_RULES:
            lessons["learned_rules"] = lessons["learned_rules"][-MAX_RULES:]
        
        save_lessons(lessons)
        print(f" Lesson Tracker: Added/updated {len(new_lessons)} rule(s)")