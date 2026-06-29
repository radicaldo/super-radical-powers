"""
runner.py — Process a claimed job end-to-end: build prompt, call model,
atomic-write files, run verify, restore on failure, requeue or fail.
Also provides run_worker() for the session worker loop.
"""
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from offload import contracts
from offload import prompt as prompt_mod
from offload.ollama_client import generate as default_generate, OllamaError

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "offload-task-prompt.md"


@dataclass
class JobOutcome:
    status: str
    verify_passed: bool
    files_written: list
    error: Optional[str]


def _safe_dest(project_dir: Path, rel_path: str) -> Path:
    """
    Resolve rel_path relative to project_dir and verify it stays inside the tree.
    Raises ValueError for absolute-escaping or out-of-tree paths (e.g. '../../.env').
    """
    root = Path(project_dir).resolve()
    dest = (root / rel_path).resolve()
    if dest != root and root not in dest.parents:
        raise ValueError(f"out-of-tree path rejected: {rel_path!r}")
    return dest


def atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via a uniquely-named temp file and os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)            # atomic on same filesystem


def _run_verify(cmd: str, cwd: Path, timeout_s: int) -> bool:
    """Run the verify command; return True on exit-0, False on non-zero, timeout, or OS error."""
    try:
        return subprocess.run(
            cmd, shell=True, cwd=str(cwd), timeout=timeout_s
        ).returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except OSError:
        return False


def _restore(snapshots: list, project_dir: Path) -> None:
    """
    Restore files to their pre-write state.

    snapshots: list of (dest_path, original_content_or_None)
      - original_content is str  → file existed; restore it
      - original_content is None → file was absent; delete it
    """
    for dest, original in snapshots:
        if original is not None:
            # File existed before — restore original content
            atomic_write(dest, original)
        else:
            # File was newly created — remove it
            dest.unlink(missing_ok=True)
            # Clean up now-empty parent directories we created
            _remove_empty_parents(dest, project_dir)


def process_job(
    job: dict,
    *,
    config: dict,
    project_dir,
    queue,
    client_generate: Callable = default_generate,
) -> JobOutcome:
    """
    Process a single claimed job end-to-end.

    1. Read payload, determine model and verify_command.
    2. Build system+user prompts.
    3. Call the model (injected via client_generate).
    4. Snapshot ALL target files FIRST (before any write).
    5. Write all files and run verify inside try/finally — restore guaranteed on failure.
    6. On pass: record complete(). On fail: restore snapshots and requeue/fail.
    """
    project_dir = Path(project_dir)
    payload = job["payload"]

    model = payload.get("model") or config["workhorse_model"]
    verify_command = payload.get("verify_command", "")

    # --- Build prompts ---
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    user_prompt = prompt_mod.build_prompt(payload, template_text)
    system_prompt = prompt_mod.SYSTEM_PROMPT

    # --- Call model ---
    result = None
    ollama_error_msg = None
    try:
        result = client_generate(
            base_url=config["base_url"],
            model=model,
            system=system_prompt,
            prompt=user_prompt,
            schema=contracts.RESULT_SCHEMA,
            num_ctx=config["num_ctx"],
            keep_alive=config["keep_alive"],
            timeout_s=config["timeout_s"],
        )
        # Validate envelope has "files" key
        if "files" not in result.envelope:
            raise OllamaError("envelope missing 'files' key")
    except OllamaError as exc:
        ollama_error_msg = f"ollama error: {exc}"

    # --- If model call failed entirely, go straight to fail path (no files to restore) ---
    if ollama_error_msg is not None:
        error = ollama_error_msg
        if job["attempts"] < config["max_attempts"]:
            queue.requeue(job["id"])
            return JobOutcome(contracts.PENDING, False, [], error)
        else:
            queue.fail(job["id"], error)
            return JobOutcome(contracts.ERROR, False, [], error)

    # --- STEP 0: Validate ALL paths up-front before any snapshot or write ---
    # If any path escapes the project tree, treat as a job failure (no files written yet).
    path_error_msg = None
    try:
        resolved_dests = [
            (_safe_dest(project_dir, f["path"]), f)
            for f in result.envelope["files"]
        ]
    except ValueError as exc:
        path_error_msg = str(exc)

    if path_error_msg is not None:
        if job["attempts"] < config["max_attempts"]:
            queue.requeue(job["id"])
            return JobOutcome(contracts.PENDING, False, [], path_error_msg)
        else:
            queue.fail(job["id"], path_error_msg)
            return JobOutcome(contracts.ERROR, False, [], path_error_msg)

    # --- STEP 1: Snapshot ALL target files BEFORE any write ---
    # snapshot: list of (dest_path, original_content_or_None)
    # None means the file was absent before we wrote it
    snapshots = []  # [(Path, str | None)]
    for dest, f in resolved_dests:
        if dest.exists():
            original = dest.read_text(encoding="utf-8")
        else:
            original = None
        snapshots.append((dest, original))

    # --- STEP 2: Write all files and verify inside try/finally ---
    files_written = []
    passed = False
    try:
        for dest, f in resolved_dests:
            atomic_write(dest, f["content"])
            files_written.append(f["path"])

        if verify_command:
            passed = _run_verify(verify_command, project_dir, config["timeout_s"])
        else:
            passed = False  # no verify command → treat as failure
    finally:
        if not passed:
            _restore(snapshots, project_dir)

    # --- STEP 3: Complete or requeue/fail ---
    if passed:
        queue.complete(
            job["id"],
            result=result.envelope,
            verify_passed=True,
            files_written=files_written,
            model=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            latency_ms=result.latency_ms,
        )
        return JobOutcome(contracts.DONE, True, files_written, None)

    # verify failed (or no verify_command)
    error = "verify failed" if verify_command else "no verify_command configured"
    if job["attempts"] < config["max_attempts"]:
        queue.requeue(job["id"])
        return JobOutcome(contracts.PENDING, False, [], error)
    else:
        queue.fail(job["id"], error)
        return JobOutcome(contracts.ERROR, False, [], error)


def _remove_empty_parents(path: Path, stop_at: Path) -> None:
    """Walk up from path.parent removing dirs that are now empty, stopping at stop_at."""
    current = path.parent
    while current != stop_at and current != current.parent:
        try:
            current.rmdir()  # only removes if empty
        except OSError:
            break  # not empty or permission error — stop
        current = current.parent


def run_worker(
    *,
    config: dict,
    project_dir,
    concurrency: int,
    idle_timeout: float,
    poll: float,
    db_path,
    client_generate: Callable = default_generate,
    stop_flag: Optional[Path] = None,
) -> None:
    """
    Session worker loop: drain pending jobs from the queue, then exit
    after idle_timeout seconds of an empty queue (or when stop_flag file exists).

    With concurrency=1, jobs are processed serially. With concurrency>1, uses
    ThreadPoolExecutor to process multiple jobs concurrently (claiming stays serial
    on the main-thread connection; each worker thread opens its own JobQueue
    connection to avoid sqlite check_same_thread violations).
    """
    from offload.queue import JobQueue
    import concurrent.futures

    project_dir = Path(project_dir)
    q = JobQueue(db_path)

    idle_since: Optional[float] = None

    try:
        while True:
            # Check stop flag
            if stop_flag is not None and Path(stop_flag).exists():
                break

            if concurrency == 1:
                # Serial path
                job = q.claim_next()
                if job is not None:
                    idle_since = None
                    process_job(
                        job,
                        config=config,
                        project_dir=project_dir,
                        queue=q,
                        client_generate=client_generate,
                    )
                else:
                    # Nothing to claim — check idle timeout
                    now = time.monotonic()
                    if idle_since is None:
                        idle_since = now
                    elif now - idle_since >= idle_timeout:
                        break
                    time.sleep(poll)
            else:
                # Concurrent path using ThreadPoolExecutor.
                # Claiming stays on the main-thread queue connection (serial).
                # Each submitted task opens its OWN JobQueue connection so that
                # complete/fail/requeue never cross thread boundaries.
                def _thread_task(job, _db_path=db_path, _config=config,
                                 _project_dir=project_dir,
                                 _client_generate=client_generate):
                    thread_q = JobQueue(_db_path)
                    try:
                        process_job(
                            job,
                            config=_config,
                            project_dir=_project_dir,
                            queue=thread_q,
                            client_generate=_client_generate,
                        )
                    finally:
                        thread_q.close()

                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                    # We enter the executor once and keep submitting until drained+idle
                    in_flight = {}  # future -> job_id
                    _idle_since: Optional[float] = None

                    while True:
                        # Check stop flag inside inner loop too
                        if stop_flag is not None and Path(stop_flag).exists():
                            break

                        # Collect completed futures
                        done_futs = [f for f in list(in_flight) if f.done()]
                        for f in done_futs:
                            del in_flight[f]
                            # surface exceptions (they were already handled in process_job)
                            try:
                                f.result()
                            except Exception:
                                pass

                        # Submit new jobs up to concurrency limit
                        while len(in_flight) < concurrency:
                            job = q.claim_next()
                            if job is None:
                                break
                            _idle_since = None
                            fut = executor.submit(_thread_task, job)
                            in_flight[fut] = job["id"]

                        if len(in_flight) == 0:
                            # No jobs in flight and nothing claimed
                            now = time.monotonic()
                            if _idle_since is None:
                                _idle_since = now
                            elif now - _idle_since >= idle_timeout:
                                break
                            time.sleep(poll)
                        else:
                            # Jobs still in flight — wait briefly
                            time.sleep(poll)

                # After executor context exits (all futures resolved), update outer idle state
                # If we broke out of the inner loop due to idle, we're done
                break
    finally:
        q.close()
