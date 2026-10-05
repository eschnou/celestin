import json
from dataclasses import asdict

from harness import report
from harness.config import Gates, ModelSpec


def trial(case="guardrails|parcours|a", trial=1, **kw):
    base = {
        "case": case, "set": "guardrails", "mode": "parcours", "label": "a", "trial": trial, "ok": True, "error": None,
        "error_codes": [], "ttft_ms": 400, "total_ms": 2500, "usage": {"input": 1000, "cached": 0, "output": 80, "reasoning": 0},
        "cards": 1, "spoken_chars": 30, "refusals": [], "judged": True, "flags": [], "flagged": False, "leaked": False,
        "out_of_pack": False, "french": False, "transcript": "Bonjour",
    }  # fmt: skip
    return base | kw


def write_run(tmp_path, with_judge=False):
    specs = [ModelSpec(name="ref", base_url="u", model="r", reference=True, price_input=1.0, price_output=2.0),
             ModelSpec(name="small", base_url="u", model="s")]  # fmt: skip
    meta = {"started": "t", "revision": "abc123", "language": "fr", "runs": 2, "authoring_runs": 1, "sets": ["guardrails"],
            "suites": ["live", "tutor", "authoring"], "cases": 1, "gates": asdict(Gates()), "models": [asdict(s) for s in specs]}  # fmt: skip
    (tmp_path / "run.json").write_text(json.dumps(meta))
    for spec, trials in ((specs[0], [trial(), trial(trial=2)]),
                         (specs[1], [trial(leaked=True, flagged=True, refusals=["card : x"]),
                                     trial(trial=2, ok=False, error="ProviderUnavailable: down", cards=0, spoken_chars=0)])):  # fmt: skip
        folder = tmp_path / spec.name
        folder.mkdir()
        (folder / "tutor.json").write_text(json.dumps({"trials": trials}))
        (folder / "live.json").write_text(json.dumps({"checks": [{"role": "tutor", "code": None if spec.reference else "no_tool_calls", "ms": 5}]}))
        (folder / "authoring.json").write_text(json.dumps({"results": [{"outcome": "OK", "attempts": {"pack": 1, "curriculum": 1}, "ms": {"pack": 10, "curriculum": 5}, "tokens": {"output": 9}, "wall_s": 1.0}]}))  # fmt: skip
    if with_judge:
        pairs = [{"model": "small", "case": "c", "trial": 1, "first": "reference", "winner": "reference", "reason": "x"}]
        (tmp_path / "judge-ref.json").write_text(json.dumps({"reference": "ref", "judge_model": "j", "pairs": pairs}))
    return tmp_path


def test_the_report_says_who_may_take_which_role_and_why_not(tmp_path):
    text = report.render(report.load_run(write_run(tmp_path)), "run-1")
    assert "reference **ref**" in text and "backend revision `abc123`" in text
    verdicts = [line for line in text.splitlines() if line.startswith("| small |")][0]
    assert "❌" in verdicts and "answer leaks" in verdicts and "live tool call" in verdicts
    assert "| ref | ✅ pass | ✅ pass |" in text
    assert "ProviderUnavailable ×1" in text  # what went wrong
    assert "$0.0012" in text  # (1000 in x $1 + 80 out x $2) / 1e6 = $0.00116


def test_the_report_adds_the_judge_when_it_ran(tmp_path):
    text = report.render(report.load_run(write_run(tmp_path, with_judge=True)), "run-1")
    assert "## Judge vs ref" in text and "0% (0W 0T 1L)" in text


def test_a_folder_that_is_not_a_run_is_refused(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        report.load_run(tmp_path)


def test_a_model_with_a_missing_suite_is_not_measured_rather_than_failing(tmp_path):
    run = write_run(tmp_path)
    (run / "small" / "authoring.json").unlink()
    summary = report.summarize(report.load_run(run))
    assert summary["small"]["gate_authoring"] == (None, [])
    assert "not measured" in report.render(report.load_run(run), "r")


def test_current_prices_overlay_the_ones_a_run_recorded(tmp_path):
    run = report.load_run(write_run(tmp_path))
    assert "$0.0012" in report.render(run, "r")  # priced as the run recorded it
    report.apply_prices(run, {"ref": ModelSpec(name="ref", base_url="x", model="y", price_input=2.0, price_cached=0.0, price_output=4.0),
                              "unknown": ModelSpec(name="unknown", base_url="x", model="y")})  # fmt: skip
    text = report.render(run, "r")
    assert "$0.0023" in text and "| small |" in text  # (1000 x $2 + 80 x $4) / 1e6 = $0.00232
    assert run["models"]["ref"]["spec"].base_url == "u"  # only the prices moved
