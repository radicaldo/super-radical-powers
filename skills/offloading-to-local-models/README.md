# offloading-to-local-models

## What It Does

An optional orchestrator variant of `subagent-driven-development` that offloads simple, self-contained, verifiable implementation tasks to a local [Ollama](https://ollama.com/) model running in a background worker — in parallel with Claude's work on the hard tasks. Every offloaded result is gated by its own `verifyCommand`; on any failure the job is retried up to `max_attempts` times, then falls back automatically. The goal is to spend near-zero Claude API tokens on boilerplate, config files, test scaffolding, utility functions, and similar low-complexity tasks.

---

## Commands

All subcommands accept `--project <root>` (defaults to the current directory).

```
python skills/offloading-to-local-models/offload_worker.py health    --project <root>
    Check that Ollama is reachable and the configured model is loaded.

python skills/offloading-to-local-models/offload_worker.py run       --project <root> --concurrency N [--idle-timeout S] [--poll S]
    Start the background worker; it drains the queue and exits when idle.
    --idle-timeout S  Seconds of empty queue before the worker exits (default: 30).
    --poll S          Queue poll interval in seconds (default: 0.5).

python skills/offloading-to-local-models/offload_worker.py gate      --project <root> --task FILE
    Evaluate a task JSON file for offload eligibility (prints pass/fail reason).

python skills/offloading-to-local-models/offload_worker.py enqueue   --project <root> --file FILE
    Add a task JSON file to the local SQLite queue.

python skills/offloading-to-local-models/offload_worker.py status    --project <root> --job-id N | --all
    Print status of a specific job or all jobs in the queue.
```

---

## Default Models and Config

| Setting | Default | Notes |
|---|---|---|
| `workhorse_model` | `qwen2.5-coder:14b` | Fits in 16 GB VRAM; primary model for offloaded tasks |
| `quality_model` | `ornith:35b-q4_K_M` | Spills to RAM, slower; a convenience default value — to use it for a given task, set that job's `model` field to the value of `config["quality_model"]` (e.g. in the task JSON before enqueuing); otherwise `workhorse_model` is used. Not an automatic tier. |
| `num_ctx` | `32768` | Context window for all requests |
| `keep_alive` | `30m` | How long Ollama keeps the model loaded between calls |
| `concurrency` | `1` | 16 GB VRAM comfortably supports up to 2 parallel workers |

The full default config is in `config.example.json`. To override settings, copy it to `<project>/.offload/config.json` and change any keys you want; unset keys fall back to the defaults.

---

## Safety Model

- **Whole-file only.** The worker never applies diffs or patches — it generates the complete file and writes it atomically, so rollback is always clean.
- **Every result is verified.** Each job specifies a `verifyCommand`; the worker runs it against the written file(s) before marking a job done. A non-zero exit rolls the file tree back to its pre-job state.
- **Auto-fallback.** Jobs that exhaust `max_attempts` land in `error` status and are handled by Claude (the normal implementer subagent) instead.
- **Hard-excluded categories.** The gate blocks jobs categorized as `security`, `algorithmic`, `concurrency`, `architecture`, or `migration` — these always go to Claude regardless of task size.

---

## IMPORTANT — Making the Skill Active (Plugin-Update Caveat)

**Making it live in Claude Code.** Claude Code loads installed plugins from a local marketplace cache, which can lag behind this source tree. A skill newly added to the source repo is **not** automatically active in a running Claude Code session until the plugin is updated/reinstalled from the fork (and a version bump is published — see `.version-bump.json`, which bumps `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `package.json` together). Until then, this skill is fully usable directly via the CLI (`python skills/offloading-to-local-models/offload_worker.py ...`) but will not be auto-discovered by the running plugin.

Do not assume the skill is live just because it exists in the source tree. Reinstall the plugin from the fork and verify the active version matches the source before expecting the skill to be auto-discovered.

---

## Phase 2 (Future)

The job contract — SQLite queue + worker process + `GenerationResult` schema — is intentionally transport-agnostic. A Phase 2 iteration can replace the in-process worker with a Dockerized FastAPI orchestrator that picks jobs from the same SQLite queue (or a Redis stream) and publishes traces to Langfuse, without any changes to the skill itself or the task scheduler. The queue schema and `contracts.py` are the stable interface boundary.
