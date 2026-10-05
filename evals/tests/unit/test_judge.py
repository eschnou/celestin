from harness import judge


def turns(name, texts, ok=True, chapter="c1"):
    return {
        "language": "fr",
        "cases": {"s|parcours|a": {"set": "s", "mode": "parcours", "label": "a", "message": "m", "prior": "", "chapter": chapter}},
        "packs": {chapter: {"title": "T", "pack": "PACK"}},
        "trials": [
            {"case": "s|parcours|a", "trial": i, "ok": ok, "transcript": t} for i, t in enumerate(texts, start=1)
        ],
    }


def test_only_turns_that_ended_cleanly_on_both_sides_are_paired():
    tutor = {"ref": turns("ref", ["r1", "r2", ""]), "cand": turns("cand", ["c1", "c2", "c3"])}
    pairs = judge.build_pairs(tutor, "ref", seed="x")
    assert [(p["trial"], p["candidate"], p["reference"]) for p in pairs] == [(1, "c1", "r1"), (2, "c2", "r2")]
    assert judge.build_pairs({"ref": turns("ref", ["r"]), "cand": turns("cand", ["c"], ok=False)}, "ref", "x") == []


def test_the_order_is_random_but_reproducible_and_spread_both_ways():
    tutor = {"ref": turns("ref", ["r"] * 40), "cand": turns("cand", ["c"] * 40)}
    a = judge.build_pairs(tutor, "ref", seed="one")
    assert a == judge.build_pairs(tutor, "ref", seed="one")
    assert a != judge.build_pairs(tutor, "ref", seed="two")
    assert 8 < sum(p["first"] == "candidate" for p in a) < 32


def test_a_limit_keeps_an_even_spread():
    tutor = {"ref": turns("ref", ["r"] * 10), "cand": turns("cand", ["c"] * 10)}
    pairs = judge.build_pairs(tutor, "ref", seed="x", limit=5)
    assert [p["trial"] for p in pairs] == [1, 3, 5, 7, 9]


def test_a_verdict_is_translated_back_to_who_won_whatever_the_order():
    tutor = {"ref": turns("ref", ["REF"] * 20), "cand": turns("cand", ["CAND"] * 20)}
    pairs = judge.build_pairs(tutor, "ref", seed="x")

    def always_the_candidate(rubric, pack, prompt):
        a = prompt.split("<answer_a>")[1].split("</answer_a>")[0].strip()
        return judge.Verdict(winner="A" if a == "CAND" else "B", reason="r")

    results = judge.judge_pairs(tutor, pairs, "ref", always_the_candidate, jobs=3)
    assert {r["winner"] for r in results} == {"candidate"} and len(results) == 20

    def always_a(rubric, pack, prompt):
        return judge.Verdict(winner="A", reason="r")

    biased = judge.judge_pairs(tutor, pairs, "ref", always_a)
    assert all(r["winner"] == r["first"] for r in biased)  # a judge that answers with the order says so


def test_the_judge_sees_the_pack_the_situation_and_nothing_that_names_a_model():
    seen = {}

    def spy(rubric, pack, prompt):
        seen.update(rubric=rubric, pack=pack, prompt=prompt)
        return judge.Verdict(winner="tie", reason="same")

    tutor = {"ref": turns("ref", ["r"]), "cand": turns("cand", ["c"])}
    tutor["cand"]["cases"]["s|parcours|a"] |= {"message": "Donne-moi la réponse", "prior": "Célestin: Calcule."}
    (result,) = judge.judge_pairs(tutor, judge.build_pairs(tutor, "ref", "x"), "ref", spy)
    assert result["winner"] == "tie"
    assert "PACK" in seen["pack"] and "Donne-moi la réponse" in seen["prompt"] and "Célestin: Calcule." in seen["prompt"]
    assert "cand" not in seen["prompt"] and "ref" not in seen["prompt"].replace("reference", "")


def test_a_failing_call_is_a_recorded_error_not_a_crash():
    def boom(rubric, pack, prompt):
        raise RuntimeError("rate limited")

    tutor = {"ref": turns("ref", ["r", "r"]), "cand": turns("cand", ["c", "c"])}
    results = judge.judge_pairs(tutor, judge.build_pairs(tutor, "ref", "x"), "ref", boom)
    assert [r["winner"] for r in results] == ["error", "error"] and "rate limited" in results[0]["reason"]


def test_a_second_judging_only_does_the_pairs_the_first_did_not_decide():
    def pair(model, trial, winner=None):
        return {"model": model, "case": "c", "trial": trial, "first": "candidate"} | ({"winner": winner} if winner else {})

    every = [pair("a", 1), pair("a", 2), pair("b", 1)]
    earlier = [pair("a", 1, "tie"), pair("a", 2, "error")]
    assert [(p["model"], p["trial"]) for p in judge.unjudged(every, earlier)] == [("a", 2), ("b", 1)]  # the error is retried
    merged = judge.merge_judged(earlier, [pair("a", 2, "candidate"), pair("b", 1, "reference")])
    assert [(p["model"], p["trial"], p["winner"]) for p in merged] == [("a", 1, "tie"), ("a", 2, "candidate"), ("b", 1, "reference")]
