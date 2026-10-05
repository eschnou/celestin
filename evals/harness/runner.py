"""The orchestrator: one worker process per model and suite, each in the backend's virtualenv.

A run is a folder, `results/<id>/`:

    run.json                    what was asked (models without keys, gates, settings, git revision)
    <model>/live.json           the provider test's live checks, repeated
    <model>/tutor.json          every probe turn, with its flags, timings, usage and transcript
    <model>/authoring.json      the authoring fixtures through the real agent
    <model>/<suite>.log         the worker's stderr

`uv run --frozen` keeps the backend's lock file as it is; the worker writes no bytecode and reads no `.env`.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from harness.config import Config, ModelSpec, worker_env

EVALS = Path(__file__).resolve().parents[1]
REPO = EVALS.parent
BACKEND = REPO / "backend"
RESULTS = EVALS / "results"


@dataclass(frozen=True)
class Plan:
    """What a run will do, for the confirmation and for `run.json`."""

    models: tuple[ModelSpec, ...]
    suites: tuple[str, ...]
    sets: tuple[str, ...]
    language: str
    runs: int
    authoring_runs: int
    turn_timeout_s: int
    cases: int  # distinct tutor cases per trial, from a free dry run (0 when unknown)
    fixtures: int

    @property
    def tutor_turns(self) -> int:
        return self.cases * self.runs * len(self.models) if "tutor" in self.suites else 0

    @property
    def authoring_runs_total(self) -> int:
        return self.fixtures * self.authoring_runs * len(self.models) if "authoring" in self.suites else 0

    def summary(self) -> str:
        lines = [f"{len(self.models)} model(s): {', '.join(m.name for m in self.models)}", f"language {self.language}"]
        if "live" in self.suites:
            lines.append(f"live checks: 3 calls x {self.runs} round(s) per model")
        if "tutor" in self.suites:
            lines.append(
                f"tutor: {self.cases} cases x {self.runs} runs x {len(self.models)} model(s) = {self.tutor_turns} turns "
                f"(sets: {', '.join(self.sets)}; a turn can be several model calls)"
            )
        if "authoring" in self.suites:
            lines.append(
                f"authoring: {self.fixtures} fixtures x {self.authoring_runs} run(s) x {len(self.models)} model(s) "
                f"= {self.authoring_runs_total} authoring runs (each is several long calls)"
            )
        return "\n".join(lines)


def uv_worker(suite: str, out: Path, plan_args: dict[str, Any], dry_run: bool = False) -> list[str]:
    """The command line of a worker. `--project` makes the backend's environment the one the code runs in."""
    command = [
        "uv", "run", "--project", str(BACKEND), "--frozen", "python", "-m", "harness.worker",
        "--suite", suite,
        "--out", str(out),
        "--language", plan_args["language"],
        "--runs", str(plan_args["authoring_runs"] if suite == "authoring" else plan_args["runs"]),
        "--sets", ",".join(plan_args["sets"]),
        "--turn-timeout", str(plan_args["turn_timeout_s"]),
    ]  # fmt: skip
    return [*command, "--dry-run"] if dry_run else command


def dry_run_counts(config: Config, language: str, sets: tuple[str, ...]) -> tuple[int, int, str]:
    """Count the cases and fixtures with a worker that makes no model call. Also proves the backend environment
    starts and the chapters load. Returns (cases, fixtures, the worker's output)."""
    spec = config.models[0]
    with tempfile.TemporaryDirectory() as scratch:
        env = worker_env(spec, dict(os.environ), scratch=Path(scratch), key="dry-run")
        args = {"language": language, "runs": 1, "authoring_runs": 1, "sets": sets, "turn_timeout_s": 1}
        outputs = {}
        for suite in ("tutor", "authoring"):
            done = subprocess.run(
                uv_worker(suite, Path(scratch) / f"{suite}.json", args, dry_run=True),
                cwd=EVALS, env=env, capture_output=True, text=True, timeout=300,
            )  # fmt: skip
            if done.returncode != 0:
                raise RuntimeError(f"the dry-run worker ({suite}) failed:\n{done.stderr[-1500:]}")
            outputs[suite] = done.stderr

    def count(text: str, pattern: str) -> int:
        import re

        found = re.search(pattern, text)
        return int(found.group(1)) if found else 0

    return (
        count(outputs["tutor"], r"dry run: (\d+) cases"),
        count(outputs["authoring"], r"dry run: (\d+) fixtures"),
        outputs["tutor"].strip(),
    )


def revision() -> str:
    try:
        done = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True)
        dirty = subprocess.run(["git", "status", "--porcelain", "backend/app", "backend/prompts"], cwd=REPO,
                               capture_output=True, text=True)  # fmt: skip
        return done.stdout.strip() + (" (+uncommitted backend changes)" if dirty.stdout.strip() else "")
    except OSError:
        return "unknown"


def new_run_dir(label: str | None = None) -> Path:
    name = datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{label}" if label else "")
    path = RESULTS / name
    path.mkdir(parents=True, exist_ok=False)
    return path


def run_model(spec: ModelSpec, plan: Plan, run_dir: Path, base_env: dict[str, str]) -> dict[str, str]:
    """Every suite for one model, one after the other. Returns the outcome per suite."""
    folder = run_dir / spec.name
    folder.mkdir(parents=True, exist_ok=True)
    outcomes: dict[str, str] = {}
    key = spec.api_key(base_env)
    if spec.api_key_env and not key:
        return {suite: f"skipped: ${spec.api_key_env} is not set" for suite in plan.suites}
    args = {
        "language": plan.language, "runs": plan.runs, "authoring_runs": plan.authoring_runs,
        "sets": plan.sets, "turn_timeout_s": plan.turn_timeout_s,
    }  # fmt: skip
    with tempfile.TemporaryDirectory() as scratch:
        env = worker_env(spec, base_env, scratch=Path(scratch))
        for suite in plan.suites:
            out = folder / f"{suite}.json"
            if out.exists():
                outcomes[suite] = "kept: already measured in this run folder"
                continue
            started = time.monotonic()
            print(f"▶ {spec.name} · {suite}", flush=True)
            with (folder / f"{suite}.log").open("w", encoding="utf-8") as log:
                done = subprocess.run(uv_worker(suite, out, args), cwd=EVALS, env=env, stdout=log, stderr=log)
            took = time.monotonic() - started
            outcomes[suite] = "ok" if done.returncode == 0 else f"worker exit {done.returncode} (see {suite}.log)"
            print(f"{'✔' if done.returncode == 0 else '✘'} {spec.name} · {suite} ({took:.0f}s) {outcomes[suite]}", flush=True)
    return outcomes


def merged_meta(existing: dict[str, Any] | None, fresh: dict[str, Any]) -> dict[str, Any]:
    """`run.json` for a resumed run: the models already in the folder stay (the report reads them from here),
    a model measured again takes its new description, the suites seen so far are the union."""
    if existing is None:
        return fresh
    models = {m["name"]: m for m in existing["models"]}
    models.update({m["name"]: m for m in fresh["models"]})
    suites = list(dict.fromkeys([*existing.get("suites", []), *fresh["suites"]]))
    return {**fresh, "started": existing.get("started", fresh["started"]), "models": list(models.values()),
            "suites": suites}  # fmt: skip


def run_all(config: Config, plan: Plan, run_dir: Path, jobs: int) -> dict[str, dict[str, str]]:
    base_env = dict(os.environ)
    fresh = {
        "started": datetime.now().isoformat(timespec="seconds"),
        "revision": revision(),
        "language": plan.language,
        "runs": plan.runs,
        "authoring_runs": plan.authoring_runs,
        "sets": list(plan.sets),
        "suites": list(plan.suites),
        "cases": plan.cases,
        "gates": asdict(config.gates),
        "models": [m.describe() for m in plan.models],
    }
    path = run_dir / "run.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    path.write_text(json.dumps(merged_meta(existing, fresh), indent=1), encoding="utf-8")
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {m.name: pool.submit(run_model, m, plan, run_dir, base_env) for m in plan.models}
        return {name: future.result() for name, future in futures.items()}
