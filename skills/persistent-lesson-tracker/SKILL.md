---
name: persistent-lesson-tracker
description: Use when running tasks on Windows or environments with repeated shell/tool command retries
---

# Persistent Lesson Tracker

## Overview

Maintains a shared `.claude/lessons.json` file that captures retry patterns, successful commands, and environment-specific lessons (especially Windows/PowerShell quirks) across tasks and sub-agents.

## When to Use

Use when:
- You want cross-task memory of "what finally worked" without re-deriving it every time
- Any project where environment friction causes repeated tool call failures
- Working on different OS environments like Windows where agents repeatedly re-learn PowerShell vs bash differences
- Running Docker, volume mounts, or shell-heavy tasks that involve retries

## Core Mechanism

This skill is **automatically active** via global hooks:
- **TaskStart** → Injects latest learned rules into the agent's context
- **TaskComplete** → Parses conversation for retry → success patterns and saves new lessons

**Script location:** `scripts/lesson-tracker.py`

## Key Features

- Automatically deduplicates rules
- Focuses on Windows/PowerShell + Docker common fixes
- Lightweight JSON store in `.claude/lessons.json`
- Visible banner at start of each task showing applied lessons

## Common Lessons It Captures

- Docker build syntax for Windows (`& docker build ...`)
- Volume mount paths
- PowerShell escaping vs bash
- No-sudo constraints, etc.

## Manual Commands

- `/persistent-lesson-tracker` (if you later add a command handler)
- Manually run `python scripts/lesson-tracker.py inject` or `parse`

## Integration Notes

This skill uses the plugin's global `hooks/hooks.json` instead of per-project settings so the tracker works everywhere without configuration.

**Related skills:** systematic-debugging, verification-before-completion