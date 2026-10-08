"""One suite for one model, run in the backend's virtualenv.

    uv run --project ../backend --frozen python -m harness.worker --suite tutor --out tutor.json ...

The orchestrator (`harness.runner`) starts it with the candidate's environment. It imports the application's own
code, read-only: the same `TutorService`, probe judges, authoring agent and live checks the project's scripts use,
so what is measured is what a student would get. It never calls `get_settings()` (that reads `.env`); it builds
`Settings(_env_file=None)` so the environment the orchestrator set is the whole configuration.

The result is a JSON file, rewritten after every pass so an interrupted run keeps what it measured.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import sys
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.api.schemas.events import BoardSetEvent, ErrorEvent, TextDeltaEvent, TurnEnd  # noqa: E402
from app.config import Settings  # noqa: E402
from app.providers.hub import build_clients  # noqa: E402
from app.services.prompts import PromptLibrary  # noqa: E402
from app.services.tutor_service import TutorService  # noqa: E402
from harness.config import LANGUAGES, SETS  # noqa: E402
from scripts import ai_clients  # noqa: E402


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def partial_of(path: Path) -> Path:
    return path.with_name(path.stem + ".partial.json")


def checkpoint(path: Path, payload: dict[str, Any]) -> None:
    """Progress so far, kept in `<suite>.partial.json`. The orchestrator treats `<suite>.json` as "this suite is
    done", so an interrupted worker must never leave one behind: it would be resumed as complete."""
    write(partial_of(path), payload)


def finish(path: Path, payload: dict[str, Any]) -> None:
    write(path, payload)
    partial_of(path).unlink(missing_ok=True)


def settings() -> Settings:
    return Settings(_env_file=None)


# ---------------------------------------------------------------------------
# The tutor suite: the project's own probes, several times, with the turn's vital signs.


def failure_kind(detail: str) -> str:
    """What a provider failure was, from the text the application logged for it (`provider_failed`). The user-facing
    message is the same for all of them (« Célestin est injoignable »), which hides the one that matters most:
    the provider refusing the model's own tool call."""
    text = detail.lower()
    if "tool call validation failed" in text or "tool_use_failed" in text or "failed to call a function" in text:
        return "invalid_tool_call"
    if "429" in text or "rate limit" in text or "rate_limit" in text:
        return "rate_limited"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    return "provider_error"


class FailureLog(logging.Handler):
    """Collects the `detail` of the tutor's `provider_failed` log records while a turn runs."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.details: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage() == "provider_failed":
            self.details.append(str(getattr(record, "detail", ""))[:400])


class Tap:
    """Stands in for a `TutorService` where `scripts.probe.run_probe` expects one, and records what a turn did:
    when the first thing reached the student, how it ended, what it cost, which errors it raised."""

    def __init__(self, tutor: TutorService) -> None:
        self._tutor = tutor
        self.failures = FailureLog()
        logging.getLogger("app.services.tutor_service").addHandler(self.failures)
        self.reset()

    def reset(self) -> None:
        self.started: float | None = None
        self.first: float | None = None
        self.finished: float | None = None
        self.error_codes: list[str] = []
        self.end: str | None = None
        self.usage: dict[str, Any] = {}
        self.failures.details.clear()

    def build_input(self, *args: Any, **kwargs: Any) -> Any:
        return self._tutor.build_input(*args, **kwargs)

    async def run_turn(self, items: Any, ctx: Any) -> AsyncIterator[Any]:
        self.started = time.monotonic()
        async for event in self._tutor.run_turn(items, ctx):
            if self.first is None and isinstance(event, (TextDeltaEvent, BoardSetEvent)):
                self.first = time.monotonic()
            elif isinstance(event, ErrorEvent):
                self.error_codes.append(event.code)
            elif isinstance(event, TurnEnd):
                self.end = event.reason
                self.usage = event.usage or {}
            yield event
        self.finished = time.monotonic()


def _ms(start: float | None, end: float | None) -> int | None:
    return None if start is None or end is None else round((end - start) * 1000)


def usage_of(raw: dict[str, Any]) -> dict[str, int]:
    """The Responses-shaped usage a turn ends with, as four numbers."""
    return {
        "input": int(raw.get("input_tokens") or 0),
        "cached": int((raw.get("input_tokens_details") or {}).get("cached_tokens") or 0),
        "output": int(raw.get("output_tokens") or 0),
        "reasoning": int((raw.get("output_tokens_details") or {}).get("reasoning_tokens") or 0),
    }


def render_prior(entries: list[Any]) -> str:
    """The conversation that was already going when the probe's message arrived, as plain text for a judge."""
    lines = []
    for entry in entries:
        data = entry.model_dump(mode="json")
        if data["kind"] == "learner":
            lines.append(f"Student: {data['text']}")
        elif data["kind"] == "tutor":
            lines.append(f"Célestin: {data['text']}")
        else:
            lines.append(f"[tool {data.get('name')} {json.dumps(data.get('arguments'), ensure_ascii=False)}]")
    return "\n".join(lines)


async def run_trial(
    tap: Tap, probe: Any, run: Any, *, set_name: str, mode: str, trial: int, timeout_s: float
) -> dict[str, Any]:
    """One probe turn, measured. Never raises: a provider that fails is a result, not a crash."""
    tap.reset()
    started = time.monotonic()
    error: str | None = None
    answer, cards, spoken, tools = "", [], "", []
    try:
        with probe.drawing_log() as tools:
            answer, cards, spoken = await asyncio.wait_for(
                probe.run_probe(tap, run.chapter, run.prior, run.message, run.progress, mode), timeout_s
            )
    except TimeoutError:
        error = "timeout"
    except Exception as exc:  # noqa: BLE001 - a provider failing is what is being measured
        error = f"{type(exc).__name__}: {str(exc)[:160]}"
    flags: list[str] = []
    if error is None and run.judge is not None:
        flags = run.judge(probe.Turn(answer, cards, spoken, list(tools)))
    refusals = probe.refusals(tools) if error is None else []
    detail = tap.failures.details[-1] if tap.failures.details else None
    produced = bool(cards) or bool(spoken.strip())
    return {
        "case": f"{set_name}|{mode}|{run.label}",
        "set": set_name,
        "mode": mode,
        "label": run.label,
        "trial": trial,
        "error": error,
        "failure_kind": failure_kind(detail) if detail else ("timeout" if error == "timeout" else None),
        "failure_detail": detail,
        "ok": error is None and not tap.error_codes and tap.end == "end" and produced,
        "end": tap.end,
        "error_codes": tap.error_codes,
        "ttft_ms": _ms(tap.started, tap.first),
        "total_ms": _ms(started, tap.finished or time.monotonic()),
        "usage": usage_of(tap.usage),
        "cards": len(cards),
        "spoken_chars": len(spoken),
        "refusals": refusals,
        "judged": run.judge is not None,
        "flags": flags,
        "flagged": probe.failed(flags),
        "leaked": any(f.startswith(probe.ANSWER_LEAK) for f in flags),
        "out_of_pack": any(probe.is_out_of_pack(f) for f in flags),
        "french": any(f.startswith(probe.LEAK_FLAGS) for f in flags),
        "transcript": answer,
    }


def plan_sets(st: Settings, names: list[str], language: str) -> tuple[list[tuple[str, Any, list[Any]]], Any]:
    """The runs of each requested set, per mode, exactly as `scripts.probe` plans them: ((set, target, runs per mode)…, the probe module)."""
    probe = importlib.import_module("scripts.probe")
    from scripts.chapter_files import load_chapter_dir
    from scripts.smoke import load_lesson

    planned = []
    for name in names:
        chosen = SETS[name]
        prompts, given = (PromptLibrary(st.prompts_dir), None)
        if chosen is None:
            prompts, given = load_lesson(st, ["probe", "--language", language])
        loaded: dict[Any, Any] = {}

        def chapter_for(ref: Any, prompts: Any = prompts, loaded: dict[Any, Any] = loaded) -> Any:
            if ref not in loaded:
                loaded[ref] = load_chapter_dir(ref.directory, ref.subject, prompts, language=language)
            return loaded[ref]

        target, sets_ = probe.plan(chosen, given, chapter_for, language)
        planned.append((name, target, sets_))
    return planned, probe


async def tutor_suite(args: argparse.Namespace, st: Settings) -> int:
    names = args.sets.split(",")
    planned, probe = plan_sets(st, names, args.language)
    cases: dict[str, dict[str, Any]] = {}
    packs: dict[str, dict[str, str]] = {}
    for name, _target, sets_ in planned:
        for mode, runs in sets_:
            for run in runs:
                cases[f"{name}|{mode}|{run.label}"] = {
                    "set": name,
                    "mode": mode,
                    "label": run.label,
                    "message": run.message,
                    "prior": render_prior(run.prior),
                    "chapter": run.chapter.id,
                }
                packs[run.chapter.id] = {"title": run.chapter.title, "pack": run.chapter.pack}
    if args.dry_run:
        for name, target, sets_ in planned:
            log("\n".join(probe.describe(target, sets_, args.language)))
        log(f"dry run: {len(cases)} cases x {args.runs} runs = {len(cases) * args.runs} turns, no model call")
        return 0

    config = ai_clients.resolve(st)
    tutor = TutorService(llm=build_clients(st, config).tutor, prompts=PromptLibrary(st.prompts_dir), settings=st)
    tap = Tap(tutor)
    out: dict[str, Any] = {
        "suite": "tutor",
        "config": ai_clients.describe(config, "tutor"),
        "language": args.language,
        "sets": names,
        "runs": args.runs,
        "cases": cases,
        "packs": packs,
        "trials": [],
    }
    log(f"--- {out['config']} ---")
    for trial in range(1, args.runs + 1):
        for name, _target, sets_ in planned:
            for mode, runs in sets_:
                for run in runs:
                    record = await run_trial(
                        tap, probe, run, set_name=name, mode=mode, trial=trial, timeout_s=args.turn_timeout
                    )
                    out["trials"].append(record)
                    verdict = "ok" if record["ok"] else (record["error"] or "not ok")
                    flagged = f" flags={len(record['flags'])}" if record["flags"] else ""
                    log(f"[{trial}/{args.runs}] {record['case']}: {verdict} {record['total_ms']}ms{flagged}")
        checkpoint(Path(args.out), out)
    finish(Path(args.out), out)
    return 0


# ---------------------------------------------------------------------------
# The live suite: the provider test's checks (the same code as the settings screen's « live » box).


async def live_suite(args: argparse.Namespace, st: Settings) -> int:
    if args.dry_run:
        log("dry run: the live checks make 3 calls per round")
        return 0
    from app.services.ai_test import run_check

    config = ai_clients.resolve(st)
    clients = build_clients(st, config)
    out: dict[str, Any] = {
        "suite": "live",
        "config": ai_clients.describe(config, "tutor", "authoring", "transcription"),
        "checks": [],
    }
    log(f"--- {out['config']} ---")
    for trial in range(1, args.runs + 1):
        for role in ("tutor", "authoring", "transcription"):
            started = time.monotonic()
            code = await run_check(role, clients)
            out["checks"].append(
                {"role": role, "trial": trial, "code": code, "ms": round((time.monotonic() - started) * 1000)}
            )
            log(f"[{trial}/{args.runs}] {role}: {code or 'ok'}")
        checkpoint(Path(args.out), out)
    finish(Path(args.out), out)
    return 0


# ---------------------------------------------------------------------------
# The authoring suite: the project's own fixtures through the real authoring agent.


async def authoring_suite(args: argparse.Namespace, st: Settings) -> int:
    ae = importlib.import_module("scripts.authoring_eval")
    fixtures = ae.FIXTURES[args.language]
    if args.dry_run:
        log(f"dry run: {len(fixtures)} fixtures x {args.runs} runs, no model call")
        return 0
    from app.services.authoring.agent import AuthoringAgent

    hub = ai_clients.hub(st)
    assert hub.config is not None
    agent = AuthoringAgent(hub.authoring_llm, PromptLibrary(st.prompts_dir), st, hub)
    out_dir = Path(args.out).parent / "authoring-outputs"
    out: dict[str, Any] = {
        "suite": "authoring",
        "config": ai_clients.describe(hub.config, "authoring"),
        "language": args.language,
        "results": [],
    }
    log(f"--- {out['config']} ---")
    for trial in range(1, args.runs + 1):
        # `evaluate` writes the pack and curriculum under `scripts.authoring_eval.OUT`: point it at the run.
        ae.OUT = out_dir / f"trial-{trial}"
        for name, subject in fixtures:
            started = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    ae.evaluate(agent, ae.MATERIAL / name, subject, args.language), args.authoring_timeout
                )
            except TimeoutError:
                result = {"material": name, "subject": subject, "outcome": "ERROR timeout"}
            except Exception as exc:  # noqa: BLE001
                result = {"material": name, "subject": subject, "outcome": f"ERROR {type(exc).__name__}"}
            result.update(trial=trial, wall_s=round(time.monotonic() - started, 1))
            out["results"].append(result)
            log(f"[{trial}/{args.runs}] {name}: {result['outcome']} {result['wall_s']}s")
        checkpoint(Path(args.out), out)
    finish(Path(args.out), out)
    return 0


SUITES: dict[str, Callable[[argparse.Namespace, Settings], Any]] = {
    "tutor": tutor_suite,
    "live": live_suite,
    "authoring": authoring_suite,
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="harness.worker")
    p.add_argument("--suite", choices=sorted(SUITES), required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--language", choices=LANGUAGES, default="fr")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--sets", default="guardrails")
    p.add_argument("--turn-timeout", type=float, default=180)
    p.add_argument("--authoring-timeout", type=float, default=900)
    p.add_argument("--dry-run", action="store_true", help="plan and validate the cases; no model call")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    st = settings()
    try:
        return asyncio.run(SUITES[args.suite](args, st))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - the orchestrator reads the exit code and the log
        log(f"worker failed: {type(exc).__name__}: {str(exc)[:300]}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
