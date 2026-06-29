"""
cli.py — Command-line interface for the offload worker.

Subcommands:
  enqueue  --file FILE        Insert a job and print its id.
  status   --job-id N | --all Print job status JSON or all jobs.
  gate     --task FILE        Evaluate eligibility and print {verdict, reason}.
  health                      Exit 0 if Ollama reachable, 1 otherwise.
  run      [--concurrency N] [--idle-timeout S] [--poll S]
                              Drain pending jobs via run_worker().
"""
import argparse
import json
import sys
from pathlib import Path

from offload import contracts, gate as gate_mod, ollama_client
from offload.queue import JobQueue
from offload import runner as runner_mod


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="offload_worker",
        description="Offload worker CLI",
    )
    parser.add_argument(
        "--project",
        default=".",
        help="Path to the project root (default: current directory)",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # --- enqueue ---
    p_enqueue = sub.add_parser("enqueue", help="Enqueue a job from a JSON file")
    p_enqueue.add_argument("--file", required=True, metavar="FILE",
                           help="Path to a JSON file containing the job payload")

    # --- status ---
    p_status = sub.add_parser("status", help="Print job status")
    status_group = p_status.add_mutually_exclusive_group(required=True)
    status_group.add_argument("--job-id", type=int, metavar="N",
                              help="Print status of a specific job")
    status_group.add_argument("--all", action="store_true",
                              help="List all jobs")

    # --- gate ---
    p_gate = sub.add_parser("gate", help="Evaluate task eligibility")
    p_gate.add_argument("--task", required=True, metavar="FILE",
                        help="Path to a JSON file containing the task dict")

    # --- health ---
    sub.add_parser("health", help="Check if Ollama is reachable")

    # --- run ---
    p_run = sub.add_parser("run", help="Run the worker to drain pending jobs")
    p_run.add_argument("--concurrency", type=int, default=None,
                       help="Number of concurrent workers (default: from config)")
    p_run.add_argument("--idle-timeout", type=float, default=30.0,
                       dest="idle_timeout",
                       help="Seconds to wait when queue is empty before exiting (default: 30)")
    p_run.add_argument("--poll", type=float, default=0.5,
                       help="Polling interval in seconds (default: 0.5)")

    return parser


def _cmd_enqueue(args, db_path: Path) -> int:
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    q = JobQueue(db_path)
    try:
        job_id = q.enqueue(payload)
        print(job_id)
        return 0
    finally:
        q.close()


def _cmd_status(args, db_path: Path) -> int:
    q = JobQueue(db_path)
    try:
        if args.all:
            print(json.dumps(q.list()))
        else:
            print(json.dumps(q.get(args.job_id)))
        return 0
    finally:
        q.close()


def _cmd_gate(args, project: Path, config: dict) -> int:
    task = json.loads(Path(args.task).read_text(encoding="utf-8"))

    # Compute max_existing_lines from disk for modify targets
    line_counts = []
    for rel_path in task.get("target_files", []):
        abs_path = project / rel_path
        if abs_path.exists():
            text = abs_path.read_text(encoding="utf-8", errors="replace")
            line_counts.append(len(text.splitlines()))

    if line_counts:
        task["max_existing_lines"] = max(line_counts)
        task["is_modify"] = True
    else:
        # Keep whatever is_modify the task already has
        if "max_existing_lines" not in task:
            task["max_existing_lines"] = None

    result = gate_mod.evaluate(task, config)
    print(json.dumps({"verdict": result.verdict, "reason": result.reason}))
    return 0


def _cmd_health(config: dict) -> int:
    ok = ollama_client.health_check(config["base_url"], timeout_s=5)
    if ok:
        print(f"Ollama reachable at {config['base_url']}")
    else:
        print(f"Ollama NOT reachable at {config['base_url']}", file=sys.stderr)
    return 0 if ok else 1


def _cmd_run(args, config: dict, project: Path, db_path: Path) -> int:
    concurrency = args.concurrency if args.concurrency is not None else config["concurrency"]
    runner_mod.run_worker(
        config=config,
        project_dir=project,
        concurrency=concurrency,
        idle_timeout=args.idle_timeout,
        poll=args.poll,
        db_path=db_path,
    )
    return 0


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    project = Path(args.project).resolve()
    db_path = contracts.offload_dir(project) / "queue.db"
    config = contracts.load_config(project)

    if args.command == "enqueue":
        return _cmd_enqueue(args, db_path)
    elif args.command == "status":
        return _cmd_status(args, db_path)
    elif args.command == "gate":
        return _cmd_gate(args, project, config)
    elif args.command == "health":
        return _cmd_health(config)
    elif args.command == "run":
        return _cmd_run(args, config, project, db_path)
    else:
        parser.print_help()
        return 1
