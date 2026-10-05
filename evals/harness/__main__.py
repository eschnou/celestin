"""The command line. Run from `evals/`:

    uv run python -m harness plan   --models models.toml
    uv run python -m harness run    --models models.toml
    uv run python -m harness report results/<run>
    uv run python -m harness judge  results/<run> --reference <model name>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harness import judge as judging
from harness import report as reporting
from harness import runner
from harness.config import SETS, SUITES, Config, ConfigError, load, load_dotenv, redact, worker_env
from harness.runner import Plan


def confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print(f"{question} — not a terminal: pass --yes to go ahead", file=sys.stderr)
        return False
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def csv(value: str | None) -> list[str] | None:
    return [part.strip() for part in value.split(",") if part.strip()] if value else None


def make_plan(args: argparse.Namespace) -> tuple[Config, Plan]:
    config = load(Path(args.models))
    models = config.select(csv(args.only))
    d = config.defaults
    suites = tuple(csv(args.suites) or d.suites)
    sets = tuple(csv(args.sets) or d.sets)
    for name in suites:
        if name not in SUITES:
            raise ConfigError(f"unknown suite {name!r}; one of {', '.join(SUITES)}")
    for name in sets:
        if name not in SETS:
            raise ConfigError(f"unknown set {name!r}; one of {', '.join(SETS)}")
    language = args.language or d.language
    cases, fixtures, _ = runner.dry_run_counts(config, language, sets)
    plan = Plan(
        models=models, suites=suites, sets=sets, language=language,
        runs=args.runs or d.runs, authoring_runs=args.authoring_runs or d.authoring_runs,
        turn_timeout_s=d.turn_timeout_s, cases=cases, fixtures=fixtures,
    )  # fmt: skip
    return config, plan


def render_run(run_dir: Path, models: str | None) -> str:
    """report.md of a run folder, with the prices currently in the candidate list (when it can be read)."""
    run = reporting.load_run(run_dir)
    if models and Path(models).exists():
        reporting.apply_prices(run, {m.name: m for m in load(Path(models)).models})
    text = reporting.render(run, run_dir.name)
    (run_dir / "report.md").write_text(text, encoding="utf-8")
    return text


def cmd_plan(args: argparse.Namespace) -> int:
    import os
    import tempfile

    config, plan = make_plan(args)
    print(plan.summary())
    print("\nWhat each worker is given (keys hidden; everything else the application reads comes from its defaults):")
    with tempfile.TemporaryDirectory() as scratch:
        for spec in plan.models:
            key = spec.api_key(dict(os.environ))
            env = worker_env(spec, dict(os.environ), scratch=Path(scratch), key=key)
            missing = f"  ← ${spec.api_key_env} is NOT set: this model would be skipped" if spec.api_key_env and not key else ""
            print(f"\n[{spec.name}]{' (reference)' if spec.reference else ''}{missing}")
            for k, v in sorted(redact(env).items()):
                if k != "DATABASE_URL":
                    print(f"  {k}={v}")
    if config.reference() is None:
        print("\nNo model is marked `reference = true`: `judge` needs one.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config, plan = make_plan(args)
    print(plan.summary())
    if not plan.cases and "tutor" in plan.suites:
        print("the dry run found no tutor cases", file=sys.stderr)
        return 1
    run_dir = Path(args.resume) if args.resume else None
    if run_dir is None:
        if not confirm("This calls the real providers and costs money. Start?", args.yes):
            return 1
        run_dir = runner.new_run_dir(args.label)
    elif not (run_dir / "run.json").exists():
        print(f"{run_dir} is not a run folder", file=sys.stderr)
        return 1
    print(f"\nrun folder: {run_dir}\n")
    outcomes = runner.run_all(config, plan, run_dir, args.jobs)
    text = render_run(run_dir, args.models)
    print("\n" + text)
    problems = {n: o for n, o in outcomes.items() if any(not (v.startswith(("ok", "kept"))) for v in o.values())}
    for name, outcome in problems.items():
        print(f"! {name}: " + "; ".join(f"{s}: {v}" for s, v in outcome.items() if not v.startswith(("ok", "kept"))), file=sys.stderr)
    print(f"report: {run_dir / 'report.md'}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    print(render_run(Path(args.run), args.models))
    return 0


def cmd_judge(args: argparse.Namespace) -> int:
    run_dir = Path(args.run)
    run = reporting.load_run(run_dir)
    names = list(run["models"])
    reference = args.reference or next((n for n, d in run["models"].items() if d["spec"].reference), None)
    if reference not in names:
        print(f"name the reference with --reference (one of {', '.join(names)})", file=sys.stderr)
        return 1
    tutor = {n: t for n in names if (t := judging.load_tutor(run_dir, n))}
    if reference not in tutor:
        print(f"{reference} has no tutor results in this run", file=sys.stderr)
        return 1
    out = run_dir / f"judge-{reference}.json"
    earlier = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    if earlier is not None and earlier["judge_model"] != args.judge_model:
        print(f"{out.name} was judged by {earlier['judge_model']}; judging more with {args.judge_model} would mix judges. "
              "Pass the same --judge-model, or move the file away.", file=sys.stderr)
        return 1
    every = judging.build_pairs(tutor, reference, seed=run_dir.name, limit=args.max_pairs)
    pairs = judging.unjudged(every, earlier["pairs"] if earlier else [])
    if earlier and every and not pairs:
        print(f"all {len(every)} pairs are already judged in {out.name}")
        return 0
    if not pairs:
        print("no pair to judge: a pair needs the same case and trial to have ended cleanly on both models", file=sys.stderr)
        return 1
    print(f"{len(pairs)} pair(s) against {reference}, judged by {args.judge_model} (about {len(pairs)} calls with the course pack in each).")
    if not confirm("This calls the Anthropic API and costs money. Go?", args.yes):
        return 1
    results = judging.judge_pairs(tutor, pairs, reference, judging.anthropic_ask(args.judge_model), args.jobs)
    merged = judging.merge_judged(earlier["pairs"] if earlier else [], results)
    out.write_text(
        json.dumps({"reference": reference, "judge_model": args.judge_model, "pairs": merged}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(render_run(run_dir, args.models))
    print(f"judged: {out}")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m harness", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def common(s: argparse.ArgumentParser) -> None:
        s.add_argument("--models", default="models.toml", help="the candidate list (default models.toml)")
        s.add_argument("--only", help="comma-separated model names")
        s.add_argument("--suites", help=f"comma-separated: {', '.join(SUITES)}")
        s.add_argument("--sets", help=f"comma-separated: {', '.join(SETS)}")
        s.add_argument("--language", choices=("fr", "en"))
        s.add_argument("--runs", type=int, help="tutor trials per case")
        s.add_argument("--authoring-runs", type=int)

    plan = sub.add_parser("plan", help="free: validate the file and the cases, show what each worker is given")
    common(plan)
    plan.set_defaults(func=cmd_plan)

    run = sub.add_parser("run", help="measure the models (costs money)")
    common(run)
    run.add_argument("--jobs", type=int, default=1, help="models measured at the same time (keep 1 for a local server)")
    run.add_argument("--label", help="added to the run folder's name")
    run.add_argument("--resume", help="a run folder: measure only what it lacks")
    run.add_argument("--yes", action="store_true", help="do not ask before spending")
    run.set_defaults(func=cmd_run)

    rep = sub.add_parser("report", help="free: rebuild report.md of a run folder")
    rep.add_argument("run")
    rep.add_argument("--models", default="models.toml", help="prices are taken from here, by model name")
    rep.set_defaults(func=cmd_report)

    judge = sub.add_parser("judge", help="rank candidates against the reference with Claude as judge (costs money)")
    judge.add_argument("run")
    judge.add_argument("--models", default="models.toml", help="prices for the report, by model name")
    judge.add_argument("--reference", help="a model name (default: the one marked `reference`)")
    judge.add_argument("--judge-model", default=judging.DEFAULT_JUDGE_MODEL)
    judge.add_argument("--max-pairs", type=int, help="judge an evenly spread subset")
    judge.add_argument("--jobs", type=int, default=4)
    judge.add_argument("--yes", action="store_true")
    judge.set_defaults(func=cmd_judge)
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv(runner.EVALS / ".env")  # API keys for the models and the judge; gitignored, never given to a worker
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, FileNotFoundError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
