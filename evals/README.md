# evals — comparing models for Célestin

A harness to answer one question: **can a smaller or open model take over a role** (tutor, authoring) from the
reference, and at what cost in quality, speed and money? It lives outside the application: it reads `backend/`
(the tutor service, the probes, the authoring agent, the provider test) and **never changes it**. Nothing in
`backend/` or `frontend/` imports it. Delete this folder and the application does not notice.

How the documentation describes it: [`documentation/model-evals.md`](../documentation/model-evals.md).

## Use

```sh
cd evals
uv sync
cp models.example.toml models.toml          # edit: one [[model]] per candidate, one marked `reference = true`

uv run python -m harness plan               # free: validates the file, loads the 16 cases, shows what each worker is given
uv run python -m harness run                # measures every model (asks before spending); writes results/<run>/report.md
uv run python -m harness run --only qwen3.8-27b-groq --suites live    # a cheap first look at one model
uv run python -m harness judge results/<run>                          # rank against the reference with Claude (needs ANTHROPIC_API_KEY)
uv run python -m harness report results/<run>                         # free: rebuild report.md
```

API keys come from the environment variable a model names (`api_key_env`), never from `models.toml`. Put them in
`evals/.env` (copy `.env.example`; gitignored, read only by the harness itself, never handed to a worker; a variable
already set in your shell wins). The backend's `.env` is not read. A local server
(Ollama, llama.cpp) needs none. `--resume results/<run>` measures only what a run folder lacks, `--jobs 2`
measures two models at once (leave it at 1 for a local server), `--runs`, `--sets`, `--language fr|en|nl` override the file. The language gate (`french_max`) applies to an English or a Dutch run.

Prices (`price_input`, `price_cached`, `price_output`, USD per million tokens) go in `models.toml`. `report` and `judge`
apply the ones currently in the file, by model name, over a past run's tokens, so prices can be filled in after a run.
Cost counts input, cached input and output; it does not see cache-write charges, and a cache stays warm across
repeated probe turns, so it is a warm-session cost.

## What it measures

Three suites per model, each a separate process running the application's own code with the candidate's
configuration and nothing else (no `.env`, no stored settings, the ambient `*_BASE_URL`/`*_MODEL`/key variables
removed):

| Suite | What runs | What comes out |
|---|---|---|
| `live` | the settings screen's live checks (`app/services/ai_test.py`), repeated | can it call `display_board` validly, follow a schema, read an image |
| `tutor` | the guardrail probes of `scripts/probe.py` (16 cases, both modes) through the real `TutorService`, `--runs` times each; `--sets` adds the drawing sets | valid turns, turns that used the board, invalid tool calls the board refused, **answer leaks**, out-of-pack formulas, French leaking into an English course, time to first token, turn time, tokens, $/turn |
| `authoring` | the fixtures of `scripts/authoring_eval.py` through the real authoring agent | valid pack and curriculum, repair attempts, time, tokens; the packs are saved to read |

The report turns this into **a verdict per role** against the `[gates]` in `models.toml` (tutor and authoring
are separate: a model can be a fine author and a useless tutor, as `gpt-oss` is on Groq), then the numbers.

`judge` adds the part a mechanical check cannot see: Claude compares each candidate turn with the reference's
for the same case and trial, shown in random order, against a rubric (teaches rather than tells; stays inside the
pack; fits the moment; voice). Only turns both models finished cleanly are judged. The report gives a score where
50% means as good as the reference, and how often the judge picked whatever it was shown first (a bias check).

## Reading the results honestly

- **One run proves nothing.** Small models are noisy; the default is 3 runs per case, and a gate on a rate needs
  more than a handful of turns. 16 cases x 3 runs is a screening, not a benchmark. Raise `--runs` for the models
  that survive.
- **Decide the gates before you look.** `[gates]` are the bar; moving them after seeing a favourite fail is how
  an eval becomes a rubber stamp.
- **`valid` is not `good`.** A model that never calls a tool still has clean turns: read `board` and the live
  check beside it.
- **The leak rate is a floor.** It counts the answers the probes know about (`secrets`), not every possible
  leak. A model at 0% here can still leak in a way nobody listed.
- **Calibrate the judge.** Read a dozen of its reasons against the transcripts (`judge-<ref>.json`,
  `<model>/tutor.json`) before believing a score, and treat a position bias far from 50% as a warning.
- **The invariants do not depend on the model.** Answers withheld, mechanical verdicts and pack-only content are
  enforced in the tools. What a weaker model costs you is teaching quality, tool-call reliability and, for
  authoring, the quality of the pack, which is why the leak and refusal numbers are *measures of how often the
  tools had to say no*.
- **Not covered:** voice (needs a Realtime server), transcription quality beyond "can it read an image", and
  authoring quality beyond "valid output" (read the saved packs; a judged authoring comparison is not built).

## Layout

| Path | What |
|---|---|
| `harness/config.py` | `models.toml` parsed and validated; the environment a worker is given |
| `harness/runner.py` | the orchestrator: one `uv run --project ../backend --frozen` process per model and suite |
| `harness/worker.py` | runs in the backend's virtualenv: the three suites, one measurement tap around the real tutor |
| `harness/metrics.py`, `report.py` | records to numbers, gates and Markdown (pure) |
| `harness/judge.py` | pairwise judging with Claude (`anthropic` SDK, `claude-opus-5-5` by default) |
| `tests/unit/` | the pure parts: `uv run pytest -q` |
| `tests/backend/` | the worker's tap against the project's own fake provider, no network: `uv run --project ../backend --frozen pytest tests/backend -p no:cacheprovider -q` |
| `results/` | one folder per run (gitignored): `run.json`, per model `live.json`, `tutor.json` (every transcript), `authoring.json`, logs, `report.md` |

## It depends on the backend's internals

The workers import `scripts.probe`, `scripts.authoring_eval`, `app.services.ai_test` and `TutorService`. That is
the point (it measures the real thing), and the price: a refactor of those names breaks the harness, loudly, in
`uv run python -m harness plan` (a free dry run) and in `tests/backend/`. Run both after changing the backend's
probes or the turn pipeline.
