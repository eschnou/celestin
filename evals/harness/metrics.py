"""Turning raw trial records into numbers and verdicts. Pure functions: no backend, no network."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from harness.config import Gates, ModelSpec


def rate(count: int, total: int) -> float | None:
    return count / total if total else None


def quantile(values: list[float], q: float) -> float | None:
    """Nearest-rank quantile: `q` in [0, 1]. No interpolation, so a small sample never invents a value."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _usage(trial: dict[str, Any], key: str) -> int:
    return int((trial.get("usage") or {}).get(key) or 0)


def cost_per_turn(trials: list[dict[str, Any]], spec: ModelSpec | None) -> float | None:
    """USD per turn from the usage the turns reported and the prices the file gives; None without prices."""
    if spec is None or not trials or not (spec.price_input or spec.price_output):
        return None
    fresh = sum(max(_usage(t, "input") - _usage(t, "cached"), 0) for t in trials)
    cached = sum(_usage(t, "cached") for t in trials)
    output = sum(_usage(t, "output") for t in trials)
    cached_price = spec.price_cached or spec.price_input
    return (fresh * spec.price_input + cached * cached_price + output * spec.price_output) / 1e6 / len(trials)


def tutor_summary(trials: list[dict[str, Any]], spec: ModelSpec | None = None) -> dict[str, Any]:
    n = len(trials)
    errored = [t for t in trials if t.get("error")]
    answered = [t for t in trials if not t.get("error")]
    return {
        "turns": n,
        "ok_rate": rate(sum(bool(t["ok"]) for t in trials), n),
        "error_rate": rate(len(errored), n),
        "empty_rate": rate(sum(1 for t in answered if not t["cards"] and not t["spoken_chars"]), n),
        "board_rate": rate(sum(1 for t in answered if t["cards"]), n),
        "refusals_per_turn": rate(sum(len(t["refusals"]) for t in trials), n),
        "leak_rate": rate(sum(bool(t["leaked"]) for t in trials), n),
        "out_of_pack_rate": rate(sum(bool(t["out_of_pack"]) for t in trials), n),
        "french_rate": rate(sum(bool(t["french"]) for t in trials), n),
        "flagged_rate": rate(sum(bool(t["flagged"]) for t in trials), n),
        "ttft_p50_ms": quantile([t["ttft_ms"] for t in answered if t.get("ttft_ms") is not None], 0.5),
        "total_p50_ms": quantile([t["total_ms"] for t in answered if t.get("total_ms") is not None], 0.5),
        "total_p95_ms": quantile([t["total_ms"] for t in answered if t.get("total_ms") is not None], 0.95),
        "input_tokens": mean([_usage(t, "input") for t in answered]),
        "output_tokens": mean([_usage(t, "output") for t in answered]),
        "cost_per_turn": cost_per_turn(answered, spec),
        "error_kinds": dict(Counter(t.get("failure_kind") or str(t["error"]).split(":")[0] for t in errored)),
        "error_codes": dict(Counter(code for t in trials for code in t.get("error_codes", []))),
    }


def by_set(trials: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for trial in trials:
        groups.setdefault(trial["set"], []).append(trial)
    return {
        name: {
            "turns": len(group),
            "ok_rate": rate(sum(bool(t["ok"]) for t in group), len(group)),
            "flagged_rate": rate(sum(bool(t["flagged"]) for t in group), len(group)),
            "refusals_per_turn": rate(sum(len(t["refusals"]) for t in group), len(group)),
        }
        for name, group in sorted(groups.items())
    }


def by_case(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per case: how many of its trials were ok and flagged. The cases a model keeps failing are the ones to read."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for trial in trials:
        groups.setdefault(trial["case"], []).append(trial)
    return sorted(
        (
            {
                "case": case,
                "trials": len(group),
                "ok": sum(bool(t["ok"]) for t in group),
                "flagged": sum(bool(t["flagged"]) for t in group),
            }
            for case, group in groups.items()
        ),
        key=lambda row: (row["ok"] - row["trials"], -row["flagged"], row["case"]),
    )


def live_summary(checks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per role: how many live checks passed, the failure codes seen, the median time."""
    out: dict[str, dict[str, Any]] = {}
    for role in sorted({c["role"] for c in checks}):
        rows = [c for c in checks if c["role"] == role]
        out[role] = {
            "passed": sum(1 for c in rows if c["code"] is None),
            "total": len(rows),
            "codes": dict(Counter(c["code"] for c in rows if c["code"])),
            "p50_ms": quantile([c["ms"] for c in rows], 0.5),
        }
    return out


def authoring_cost_per_run(results: list[dict[str, Any]], spec: ModelSpec | None) -> float | None:
    """USD per authoring run (a fixture through the whole agent) from the tokens it reported; None without prices."""
    if spec is None or not results or not (spec.price_input or spec.price_output):
        return None
    total = 0.0
    for r in results:
        t = r.get("tokens") or {}
        fresh = max(int(t.get("input") or 0) - int(t.get("cached") or 0), 0)
        total += fresh * spec.price_input + int(t.get("cached") or 0) * (spec.price_cached or spec.price_input)
        total += int(t.get("output") or 0) * spec.price_output
    return total / 1e6 / len(results)


def authoring_summary(results: list[dict[str, Any]], spec: ModelSpec | None = None) -> dict[str, Any]:
    ok = [r for r in results if r.get("outcome") == "OK"]
    attempts = [sum((r.get("attempts") or {}).values()) for r in ok]
    return {
        "fixtures": len(results),
        "ok_rate": rate(len(ok), len(results)),
        "attempts_mean": mean(attempts),
        "pack_p50_ms": quantile([r["ms"]["pack"] for r in ok if r.get("ms")], 0.5),
        "curriculum_p50_ms": quantile([r["ms"]["curriculum"] for r in ok if r.get("ms")], 0.5),
        "output_tokens": mean([(r.get("tokens") or {}).get("output", 0) for r in results]),
        "cost_per_run": authoring_cost_per_run(results, spec),
        "wall_p50_s": quantile([r["wall_s"] for r in results if r.get("wall_s") is not None], 0.5),
        "failures": dict(Counter(str(r["outcome"]) for r in results if r.get("outcome") != "OK")),
    }


def _below(value: float | None, minimum: float, label: str, reasons: list[str]) -> None:
    if value is None:
        reasons.append(f"{label}: not measured")
    elif value < minimum:
        reasons.append(f"{label} {value:.0%} < {minimum:.0%}")


def _above(value: float | None, maximum: float, label: str, reasons: list[str]) -> None:
    if value is not None and value > maximum:
        reasons.append(f"{label} {value:.1%} > {maximum:.1%}")


def gate_tutor(
    tutor: dict[str, Any] | None, live: dict[str, dict[str, Any]] | None, gates: Gates, language: str
) -> tuple[bool | None, list[str]]:
    """Whether a model may take the tutor role: None when nothing was measured, else the verdict and why not."""
    if tutor is None and not live:
        return None, []
    reasons: list[str] = []
    if live and "tutor" in live:
        check = live["tutor"]
        _below(rate(check["passed"], check["total"]), gates.live_tutor_min, "live tool call", reasons)
    if tutor is not None:
        _below(tutor["ok_rate"], gates.tutor_ok_min, "valid turns", reasons)
        _above(tutor["leak_rate"], gates.leak_max, "answer leaks", reasons)
        _above(tutor["out_of_pack_rate"], gates.out_of_pack_max, "out-of-pack", reasons)
        if language != "fr":
            # The probes' « leakage »: French in an English course, French or English in a Dutch one.
            _above(tutor["french_rate"], gates.french_max, "language leaks", reasons)
    return not reasons, reasons


def gate_authoring(authoring: dict[str, Any] | None, gates: Gates) -> tuple[bool | None, list[str]]:
    if authoring is None:
        return None, []
    reasons: list[str] = []
    _below(authoring["ok_rate"], gates.authoring_ok_min, "authoring", reasons)
    return not reasons, reasons


def judge_summary(pairs: list[dict[str, Any]], model: str) -> dict[str, Any] | None:
    """The judged pairs of one candidate against the reference: wins, ties, losses and the judge's own bias."""
    rows = [p for p in pairs if p["model"] == model]
    if not rows:
        return None
    decided = [p for p in rows if p["winner"] in ("candidate", "reference", "tie")]
    wins = sum(p["winner"] == "candidate" for p in decided)
    losses = sum(p["winner"] == "reference" for p in decided)
    ties = sum(p["winner"] == "tie" for p in decided)
    return {
        "pairs": len(rows),
        "errors": len(rows) - len(decided),
        "wins": wins,
        "ties": ties,
        "losses": losses,
        # Ties count half, the usual convention: 50 % means as good as the reference.
        "score": rate(2 * wins + ties, 2 * len(decided)),
    }


def position_bias(pairs: list[dict[str, Any]]) -> float | None:
    """Among decisive verdicts, the share that picked the response shown first. Far from 50 % means the judge
    is answering with the order, and its scores should be read with that in mind."""
    decisive = [p for p in pairs if p["winner"] in ("candidate", "reference")]
    if not decisive:
        return None
    first = sum(p["winner"] == p["first"] for p in decisive)
    return first / len(decisive)
