"""A run folder read into one Markdown report. Pure: it only reads JSON."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from harness import metrics
from harness.config import Gates, ModelSpec


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def pct(value: float | None, digits: int = 0) -> str:
    return "–" if value is None else f"{value * 100:.{digits}f}%"


def ms(value: float | None) -> str:
    if value is None:
        return "–"
    return f"{value / 1000:.1f}s" if value >= 1000 else f"{value:.0f}ms"


def num(value: float | None, digits: int = 0) -> str:
    return "–" if value is None else f"{value:,.{digits}f}"


def money(value: float | None) -> str:
    return "–" if value is None else f"${value:.4f}"


def table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(out)


def load_run(run_dir: Path) -> dict[str, Any]:
    """Everything a run folder holds, per model, plus any judge files."""
    meta = _load(run_dir / "run.json")
    if meta is None:
        raise FileNotFoundError(f"{run_dir} has no run.json: not a run folder")
    models = {}
    for spec in meta["models"]:
        folder = run_dir / spec["name"]
        models[spec["name"]] = {
            "spec": ModelSpec(**spec),
            "live": _load(folder / "live.json"),
            "tutor": _load(folder / "tutor.json"),
            "authoring": _load(folder / "authoring.json"),
        }
    judges = [j for p in sorted(run_dir.glob("judge-*.json")) if (j := _load(p))]
    return {"meta": meta, "models": models, "judges": judges}


def apply_prices(run: dict[str, Any], specs: dict[str, ModelSpec]) -> None:
    """Today's prices from `models.toml` over the ones a run recorded, by model name. Prices change and are often
    filled in after a run; the tokens it measured do not, so the cost is recomputed and nothing else is touched."""
    for name, data in run["models"].items():
        current = specs.get(name)
        if current is not None:
            data["spec"] = replace(
                data["spec"], price_input=current.price_input, price_cached=current.price_cached,
                price_output=current.price_output,
            )  # fmt: skip


def summarize(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The numbers per model: what the tables show and the gates read."""
    meta = run["meta"]
    gates = Gates(**meta["gates"])
    pairs = [p for j in run["judges"] for p in j["pairs"]]
    out: dict[str, dict[str, Any]] = {}
    for name, data in run["models"].items():
        tutor = metrics.tutor_summary(data["tutor"]["trials"], data["spec"]) if data["tutor"] else None
        live = metrics.live_summary(data["live"]["checks"]) if data["live"] else None
        authoring = metrics.authoring_summary(data["authoring"]["results"], data["spec"]) if data["authoring"] else None
        out[name] = {
            "tutor": tutor,
            "live": live,
            "authoring": authoring,
            "by_set": metrics.by_set(data["tutor"]["trials"]) if data["tutor"] else {},
            "cases": metrics.by_case(data["tutor"]["trials"]) if data["tutor"] else [],
            "judge": metrics.judge_summary(pairs, name),
            "gate_tutor": metrics.gate_tutor(tutor, live, gates, meta["language"]),
            "gate_authoring": metrics.gate_authoring(authoring, gates),
        }
    return out


def verdict(result: tuple[bool | None, list[str]]) -> str:
    passed, reasons = result
    if passed is None:
        return "not measured"
    return "✅ pass" if passed else "❌ " + "; ".join(reasons)


def render(run: dict[str, Any], run_name: str) -> str:
    meta, summary = run["meta"], summarize(run)
    names = list(run["models"])
    reference = next((n for n, d in run["models"].items() if d["spec"].reference), None)
    out = [
        f"# Model comparison — {run_name}",
        "",
        f"Course language **{meta['language']}** · {meta['runs']} run(s) per tutor case · sets: {', '.join(meta['sets'])} · "
        f"{meta['cases']} cases · authoring runs: {meta['authoring_runs']} · backend revision `{meta['revision']}`"
        + (f" · reference **{reference}**" if reference else ""),
        "",
        "## Verdict by role",
        "",
        "A model is allowed a role only if it clears the gates in `models.toml` (the numbers are below). "
        "The judge, when it ran, is for ranking models that already pass.",
        "",
        table(
            ["model", "tutor", "authoring"],
            [[n, verdict(summary[n]["gate_tutor"]), verdict(summary[n]["gate_authoring"])] for n in names],
        ),
    ]

    if any(summary[n]["tutor"] for n in names):
        out += [
            "",
            "## Tutor",
            "",
            "`valid` = the turn ended cleanly with something shown (no provider error, no tool error, "
            "a finished turn): a model that never calls a tool still scores well here, so read `board` (turns that put a card "
            "on the board) next to the reference's, and the live check below. `refusals` = invalid tool calls the board refused, per turn: the first thing "
            "that breaks on a small model. `leak`, `out-of-pack` and `french` come from the probes' mechanical judges.",
            "",
        ]
        rows = []
        for n in names:
            t = summary[n]["tutor"]
            if t is None:
                rows.append([n] + ["–"] * 13)
                continue
            judge = summary[n]["judge"]
            rows.append([
                n, str(t["turns"]), pct(t["ok_rate"]), pct(t["board_rate"]), num(t["refusals_per_turn"], 2), pct(t["leak_rate"], 1),
                pct(t["out_of_pack_rate"], 1), pct(t["french_rate"], 1), ms(t["ttft_p50_ms"]), ms(t["total_p50_ms"]),
                ms(t["total_p95_ms"]), f"{num(t['input_tokens'])} / {num(t['output_tokens'])}",
                money(t["cost_per_turn"]),
                "–" if judge is None else f"{pct(judge['score'])} ({judge['wins']}W {judge['ties']}T {judge['losses']}L)",
            ])  # fmt: skip
        out.append(table(
            ["model", "turns", "valid", "board", "refusals", "leak", "out-of-pack", "french", "TTFT p50", "turn p50", "turn p95",
             "tokens in / out", "$/turn", "judge vs ref"],
            rows,
        ))  # fmt: skip
        failures = [(n, summary[n]["tutor"]) for n in names if summary[n]["tutor"] and (summary[n]["tutor"]["error_kinds"] or summary[n]["tutor"]["error_codes"])]
        if failures:
            out += ["", "### What went wrong", "",
                    "`invalid_tool_call`: the provider refused the model's own tool call (Groq validates arguments server-side and aborts "
                    "the turn, so the application's own correction loop never runs: a recoverable mistake becomes a dead turn). "
                    "`rate_limited`, `timeout`, `provider_error`: the provider or the network, not the model.", ""]
            for n, t in failures:
                parts = [f"{k} ×{v}" for k, v in t["error_kinds"].items()] + [f"event `{k}` ×{v}" for k, v in t["error_codes"].items()]
                out.append(f"- **{n}**: " + ", ".join(parts))
        sets_rows = [[n, s, str(v["turns"]), pct(v["ok_rate"]), pct(v["flagged_rate"]), num(v["refusals_per_turn"], 2)]
                     for n in names for s, v in summary[n]["by_set"].items()]  # fmt: skip
        if len(meta["sets"]) > 1 and sets_rows:
            out += ["", "### By set", "", table(["model", "set", "turns", "valid", "flagged", "refusals"], sets_rows)]
        weak = {n: [c for c in summary[n]["cases"] if c["ok"] < c["trials"] or c["flagged"]][:5] for n in names}
        if any(weak.values()):
            out += ["", "### Cases to read", "", "The cases each model passed least often (the transcripts are in `<model>/tutor.json`).", ""]
            for n, cases in weak.items():
                if cases:
                    out.append(f"- **{n}**: " + "; ".join(f"{c['case']} (valid {c['ok']}/{c['trials']}, flagged {c['flagged']})" for c in cases))

    if any(summary[n]["live"] for n in names):
        out += ["", "## Live checks", "", "The settings screen's « live » test, repeated: can the model do the role's basic job?", ""]
        rows = []
        for n in names:
            live = summary[n]["live"] or {}
            rows.append([n] + [
                (f"{live[r]['passed']}/{live[r]['total']}" + (" " + ", ".join(f"`{c}`" for c in live[r]["codes"]) if live[r]["codes"] else ""))
                if r in live else "–"
                for r in ("tutor", "authoring", "transcription")
            ])  # fmt: skip
        out.append(table(["model", "tutor (tool call)", "authoring (schema)", "transcription (image)"], rows))

    if any(summary[n]["authoring"] for n in names):
        out += ["", "## Authoring", "", "The fixtures in `backend/tests/fixtures/material`, through the real agent. Quality is for reading: "
                "the packs are in `<model>/authoring-outputs/` (formulas copied from the material, « Points à vérifier » where it is wrong, "
                "no instruction from the injection fixture obeyed).", ""]  # fmt: skip
        rows = []
        for n in names:
            a = summary[n]["authoring"]
            rows.append([n, "–" if a is None else f"{pct(a['ok_rate'])} of {a['fixtures']}", "–" if a is None else num(a["attempts_mean"], 1),
                         "–" if a is None else ms(a["pack_p50_ms"]), "–" if a is None else ms(a["curriculum_p50_ms"]),
                         "–" if a is None else num(a["output_tokens"]), "–" if a is None else money(a["cost_per_run"]), "–" if a is None else (", ".join(f"{k} ×{v}" for k, v in a["failures"].items()) or "–")])  # fmt: skip
        out.append(table(["model", "valid", "attempts (ok)", "pack p50", "curriculum p50", "output tokens", "$/run", "failures"], rows))

    for judge in run["judges"]:
        bias = metrics.position_bias(judge["pairs"])
        out += ["", f"## Judge vs {judge['reference']}", "",
                f"Judge `{judge['judge_model']}`, {len(judge['pairs'])} pairs, order randomised. Score = (wins + ½ ties) / pairs: 50% is as good as the reference. "
                f"Share of decisive verdicts that picked the response shown first: **{pct(bias)}** "
                "(far from 50% and the judge is partly answering with the order).",
                "", "The judge's reasons are in `judge-" + judge["reference"] + ".json`; read a dozen against the transcripts before trusting the score."]  # fmt: skip
    out.append("")
    return "\n".join(out)
