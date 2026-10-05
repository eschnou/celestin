from pathlib import Path

import pytest

from harness.config import AMBIENT_AI_VARS, ConfigError, ModelSpec, load, load_dotenv, parse, redact, worker_env

EXAMPLE = Path(__file__).resolve().parents[2] / "models.example.toml"


def raw(**model):
    base = {"name": "m", "base_url": "http://localhost:1/v1", "model": "x"}
    return {"model": [base | model]}


def test_the_example_file_is_valid():
    config = load(EXAMPLE)
    assert [m.name for m in config.models] == ["gpt-6.1-sol-medium", "gpt-6.1-sol-high", "qwen3.8-27b-groq", "local-ollama"]
    assert config.reference().name == "gpt-6.1-sol-high"
    assert config.defaults.runs == 3 and config.gates.leak_max == 0.01


@pytest.mark.parametrize(
    "bad, message",
    [
        ({}, "names no"),
        ({"model": [{"name": "a b", "base_url": "u", "model": "m"}]}, "must be letters"),
        ({"model": [{"name": "a", "base_url": "u"}]}, "`model` is required"),
        ({"model": [{"name": "a", "base_url": "u", "model": "m", "api_style": "grpc"}]}, "api_style"),
        ({"model": [{"name": "a", "base_url": "u", "model": "m", "typo": 1}]}, "unknown key"),
        ({"defaults": {"sets": ["nope"]}, "model": [{"name": "a", "base_url": "u", "model": "m"}]}, "not one of"),
        ({"defaults": {"runs": 0}, "model": [{"name": "a", "base_url": "u", "model": "m"}]}, "at least 1"),
        ({"gates": {"leak": 1}, "model": [{"name": "a", "base_url": "u", "model": "m"}]}, "unknown key"),
        ({"model": [{"name": "a", "base_url": "u", "model": "m"}] * 2}, "unique"),
        (
            {"model": [{"name": n, "base_url": "u", "model": "m", "reference": True} for n in "ab"]},
            "at most one",
        ),
    ],
)
def test_a_wrong_file_says_what_is_wrong(bad, message):
    with pytest.raises(ConfigError, match=message):
        parse(bad)


def test_select_names_the_unknown_model():
    config = parse(raw())
    assert config.select(None) == config.models and config.select(["m"])[0].name == "m"
    with pytest.raises(ConfigError, match="unknown model"):
        config.select(["z"])


def test_a_worker_gets_the_spec_and_nothing_ambient(tmp_path):
    ambient = {
        "PATH": "/bin",
        "OPENAI_API_KEY": "sk-ambient",
        "TUTOR_BASE_URL": "http://elsewhere",
        "AUTHORING_REASONING_EFFORT": "high",
        "SECRETS_DIR": "/secrets",
        "GROQ_API_KEY": "gsk-1234567890",
    }
    spec = ModelSpec(name="g", base_url="https://api.groq.com/openai/v1", model="q", api_key_env="GROQ_API_KEY",
                     api_style="chat", structured="json", authoring_model="a", tutor_effort="")  # fmt: skip
    env = worker_env(spec, ambient, scratch=tmp_path)
    assert env["OPENAI_API_KEY"] == "gsk-1234567890"
    assert env["OPENAI_BASE_URL"] == "https://api.groq.com/openai/v1"
    assert (env["OPENAI_MODEL"], env["AUTHORING_MODEL"], env["TRANSCRIPTION_MODEL"]) == ("q", "a", "q")
    assert (env["AI_API_STYLE"], env["AI_STRUCTURED_OUTPUTS"]) == ("chat", "json")
    assert env["TUTOR_REASONING_EFFORT"] == ""  # "" is "not sent", which is a setting
    assert "AUTHORING_REASONING_EFFORT" not in env  # the ambient one is gone; none was asked for
    assert "TUTOR_BASE_URL" not in env and "SECRETS_DIR" not in env
    assert env["PATH"] == "/bin" and env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["DATABASE_URL"].endswith("no-such.db") and not (tmp_path / "no-such.db").exists()


def test_a_keyless_server_gets_no_key_even_if_one_is_ambient(tmp_path):
    spec = ModelSpec(name="l", base_url="http://localhost:11434/v1", model="q")
    assert "OPENAI_API_KEY" not in worker_env(spec, {"OPENAI_API_KEY": "sk-ambient"}, scratch=tmp_path)


def test_the_plan_never_prints_a_key(tmp_path):
    spec = ModelSpec(name="g", base_url="u", model="q", api_key_env="K")
    shown = redact(worker_env(spec, {"K": "sk-very-secret-1234"}, scratch=tmp_path))
    assert "secret" not in str(shown) and shown["OPENAI_API_KEY"] == "…1234"
    assert "OPENAI_API_KEY" in AMBIENT_AI_VARS


def test_efforts_expand_a_model_into_one_variant_per_level():
    config = parse({"model": [{"name": "sol", "base_url": "u", "model": "m", "reference": True, "efforts": ["medium", "high"]},
                              {"name": "q", "base_url": "u", "model": "m", "efforts": ["high"]}]})  # fmt: skip
    assert [m.name for m in config.models] == ["sol-medium", "sol-high", "q-high"]
    assert [m.effort for m in config.models] == ["medium", "high", "high"]
    assert [m.reference for m in config.models] == [False, True, False]  # the last level, unless told otherwise


def test_reference_effort_picks_the_reference_variant():
    config = parse({"model": [{"name": "sol", "base_url": "u", "model": "m", "reference": True,
                               "efforts": ["medium", "high"], "reference_effort": "medium"}]})  # fmt: skip
    assert [m.reference for m in config.models] == [True, False]


@pytest.mark.parametrize(
    "extra, message",
    [
        ({"efforts": []}, "non-empty"),
        ({"efforts": ["high", "high"]}, "without repeats"),
        ({"efforts": ["extreme"]}, "not one of"),
        ({"efforts": ["high"], "effort": "high"}, "not both"),
        ({"efforts": ["high"], "reference_effort": "low"}, "not in `efforts`"),
        ({"reference_effort": "low"}, "needs `efforts`"),
        ({"effort": "extreme"}, "not one of"),
        ({"tutor_effort": "max"}, "not one of"),
    ],
)
def test_wrong_effort_settings_are_refused(extra, message):
    with pytest.raises(ConfigError, match=message):
        parse(raw(**extra))


def test_effort_is_the_shorthand_for_tutor_and_authoring_and_a_roles_own_wins(tmp_path):
    spec = ModelSpec(name="m", base_url="u", model="x", effort="high", authoring_effort="low")
    env = worker_env(spec, {}, scratch=tmp_path)
    assert env["TUTOR_REASONING_EFFORT"] == "high" and env["AUTHORING_REASONING_EFFORT"] == "low"
    assert "TRANSCRIPTION_REASONING_EFFORT" not in env  # reading a page is not a place to think hard
    assert "TUTOR_REASONING_EFFORT" not in worker_env(ModelSpec(name="m", base_url="u", model="x"), {}, scratch=tmp_path)


def test_dotenv_adds_keys_without_overriding_the_shell(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# keys\nGROQ_API_KEY=gsk-1\nexport OPENAI_API_KEY = \"sk-2\"\nEMPTY=\nANTHROPIC_API_KEY='sk-ant-3'\nnot a line\n")
    environ = {"OPENAI_API_KEY": "from-the-shell"}
    assert load_dotenv(f, environ) == ["GROQ_API_KEY", "ANTHROPIC_API_KEY"]
    assert environ == {"OPENAI_API_KEY": "from-the-shell", "GROQ_API_KEY": "gsk-1", "ANTHROPIC_API_KEY": "sk-ant-3"}
    assert load_dotenv(tmp_path / "missing", {}) == []


def test_the_authoring_output_cap_reaches_the_worker_and_is_validated(tmp_path):
    spec = ModelSpec(name="g", base_url="u", model="q", authoring_max_output_tokens=16000)
    assert worker_env(spec, {"AUTHORING_MAX_OUTPUT_TOKENS": "99"}, scratch=tmp_path)["AUTHORING_MAX_OUTPUT_TOKENS"] == "16000"
    plain = ModelSpec(name="g", base_url="u", model="q")
    assert "AUTHORING_MAX_OUTPUT_TOKENS" not in worker_env(plain, {"AUTHORING_MAX_OUTPUT_TOKENS": "99"}, scratch=tmp_path)
    with pytest.raises(ConfigError, match="at least 1000"):
        parse(raw(authoring_max_output_tokens=10))
