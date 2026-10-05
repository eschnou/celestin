from harness.runner import merged_meta


def model(name, **kw):
    return {"name": name, "model": "x"} | kw


def test_a_fresh_run_is_written_as_it_is():
    fresh = {"started": "t1", "suites": ["live"], "models": [model("a")]}
    assert merged_meta(None, fresh) == fresh


def test_a_resumed_run_keeps_the_models_already_measured():
    existing = {"started": "t0", "suites": ["live", "tutor"], "models": [model("a"), model("b")], "runs": 3}
    fresh = {"started": "t1", "suites": ["tutor", "authoring"], "models": [model("c"), model("b", effort="high")], "runs": 3}
    merged = merged_meta(existing, fresh)
    assert [m["name"] for m in merged["models"]] == ["a", "b", "c"]
    assert merged["models"][1]["effort"] == "high"  # measured again: the new description
    assert merged["started"] == "t0" and merged["suites"] == ["live", "tutor", "authoring"]
