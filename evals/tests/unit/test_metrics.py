from harness import metrics
from harness.config import Gates, ModelSpec


def trial(**kw):
    base = {
        "case": "guardrails|parcours|a", "set": "guardrails", "trial": 1, "ok": True, "error": None, "error_codes": [],
        "ttft_ms": 100, "total_ms": 1000, "usage": {"input": 1000, "cached": 400, "output": 100, "reasoning": 0},
        "cards": 1, "spoken_chars": 20, "refusals": [], "flagged": False, "leaked": False, "out_of_pack": False,
        "french": False,
    }
    return base | kw


def test_quantiles_never_invent_a_value():
    assert metrics.quantile([], 0.5) is None
    assert metrics.quantile([5], 0.95) == 5
    assert metrics.quantile([1, 2, 3, 4], 0.5) == 2 and metrics.quantile([1, 2, 3, 4], 0.95) == 4


def test_tutor_summary_counts_what_went_wrong():
    trials = [
        trial(),
        trial(refusals=["card : per_card", "card : x"], flagged=True, leaked=True),
        trial(ok=False, error="ProviderUnavailable: boom", ttft_ms=None, total_ms=50, cards=0, spoken_chars=0),
        trial(ok=False, error_codes=["tool_failed"], cards=0, spoken_chars=0),
    ]
    s = metrics.tutor_summary(trials)
    assert s["turns"] == 4 and s["ok_rate"] == 0.5 and s["error_rate"] == 0.25
    assert s["leak_rate"] == 0.25 and s["refusals_per_turn"] == 0.5 and s["flagged_rate"] == 0.25
    assert s["empty_rate"] == 0.25  # answered without error, but showed nothing
    assert s["board_rate"] == 0.5  # two of the four turns put a card on the board
    assert s["error_kinds"] == {"ProviderUnavailable": 1} and s["error_codes"] == {"tool_failed": 1}
    assert s["ttft_p50_ms"] == 100  # the failed turn has no first token and is left out


def test_cost_needs_prices_and_counts_cached_input_at_its_own_rate():
    spec = ModelSpec(name="m", base_url="u", model="m", price_input=2.0, price_cached=0.5, price_output=10.0)
    t = [trial()]  # 600 fresh, 400 cached, 100 out
    expected = (600 * 2.0 + 400 * 0.5 + 100 * 10.0) / 1e6
    assert metrics.cost_per_turn(t, spec) == expected
    assert metrics.cost_per_turn(t, ModelSpec(name="m", base_url="u", model="m")) is None
    assert metrics.cost_per_turn([], spec) is None


def test_by_case_puts_the_worst_first():
    rows = metrics.by_case([trial(case="a"), trial(case="b", ok=False), trial(case="b", flagged=True), trial(case="c")])
    assert [r["case"] for r in rows] == ["b", "a", "c"]
    assert rows[0] == {"case": "b", "trials": 2, "ok": 1, "flagged": 1}


def test_live_summary():
    checks = [{"role": "tutor", "code": None, "ms": 10}, {"role": "tutor", "code": "no_tool_calls", "ms": 30}]
    assert metrics.live_summary(checks) == {"tutor": {"passed": 1, "total": 2, "codes": {"no_tool_calls": 1}, "p50_ms": 10}}


def test_authoring_summary():
    ok = {"outcome": "OK", "attempts": {"pack": 2, "curriculum": 1}, "ms": {"pack": 100, "curriculum": 50},
          "tokens": {"output": 10}, "wall_s": 3.0}  # fmt: skip
    bad = {"outcome": "FAILED schema at pack", "tokens": {"output": 30}, "wall_s": 9.0}
    s = metrics.authoring_summary([ok, bad])
    assert s["ok_rate"] == 0.5 and s["attempts_mean"] == 3 and s["failures"] == {"FAILED schema at pack": 1}


def test_the_tutor_gate_names_each_failed_requirement():
    gates = Gates()
    good = metrics.tutor_summary([trial() for _ in range(20)])
    assert metrics.gate_tutor(good, {"tutor": {"passed": 3, "total": 3}}, gates, "fr") == (True, [])
    bad = metrics.tutor_summary([trial(leaked=True)] + [trial(ok=False, error="x", cards=0, spoken_chars=0)] * 3)
    passed, reasons = metrics.gate_tutor(bad, {"tutor": {"passed": 2, "total": 3}}, gates, "fr")
    assert passed is False
    assert any("live tool call" in r for r in reasons) and any("valid turns" in r for r in reasons)
    assert any("answer leaks" in r for r in reasons)
    assert metrics.gate_tutor(None, None, gates, "fr") == (None, [])


def test_french_leaks_only_count_for_an_english_course():
    leaky = metrics.tutor_summary([trial(french=True)])
    assert metrics.gate_tutor(leaky, None, Gates(), "fr")[0] is True
    assert metrics.gate_tutor(leaky, None, Gates(), "en")[0] is False


def test_an_unmeasured_requirement_is_not_a_pass():
    assert metrics.gate_authoring(metrics.authoring_summary([]), Gates()) == (False, ["authoring: not measured"])
    assert metrics.gate_authoring(None, Gates()) == (None, [])


def test_judge_score_counts_ties_half_and_bias_is_the_share_picking_the_first():
    pairs = [
        {"model": "m", "winner": "candidate", "first": "candidate"},
        {"model": "m", "winner": "reference", "first": "candidate"},
        {"model": "m", "winner": "tie", "first": "reference"},
        {"model": "m", "winner": "error", "first": "reference"},
        {"model": "other", "winner": "candidate", "first": "candidate"},
    ]
    s = metrics.judge_summary(pairs, "m")
    assert (s["wins"], s["ties"], s["losses"], s["errors"]) == (1, 1, 1, 1) and s["score"] == 0.5
    assert metrics.judge_summary(pairs, "none") is None
    assert metrics.position_bias(pairs[:2]) == 0.5
    assert metrics.position_bias([{"winner": "tie", "first": "candidate"}]) is None


def test_failures_are_counted_by_cause_not_by_the_message_the_student_sees():
    trials = [
        trial(ok=False, error="ProviderUnavailable: Célestin est injoignable", failure_kind="invalid_tool_call"),
        trial(ok=False, error="ProviderUnavailable: Célestin est injoignable", failure_kind="invalid_tool_call"),
        trial(ok=False, error="timeout", failure_kind="timeout"),
        trial(ok=False, error="ProviderUnavailable: x"),  # an older record without a cause
    ]
    assert metrics.tutor_summary(trials)["error_kinds"] == {"invalid_tool_call": 2, "timeout": 1, "ProviderUnavailable": 1}


def test_authoring_cost_per_run_uses_the_three_prices():
    spec = ModelSpec(name="m", base_url="u", model="m", price_input=2.0, price_cached=0.5, price_output=10.0)
    runs = [{"tokens": {"input": 1000, "cached": 400, "output": 100}}, {"tokens": {"input": 0, "cached": 0, "output": 0}}]
    assert metrics.authoring_cost_per_run(runs, spec) == ((600 * 2.0 + 400 * 0.5 + 100 * 10.0) / 1e6) / 2
    assert metrics.authoring_cost_per_run(runs, ModelSpec(name="m", base_url="u", model="m")) is None
    assert metrics.authoring_summary([{"outcome": "OK", "tokens": {"output": 1}}], spec)["cost_per_run"] is not None
