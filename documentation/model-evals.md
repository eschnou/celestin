# Model evaluations

How to find out whether a smaller or open model can take a role (tutor, authoring) from the reference. The
harness is `evals/`, a separate uv project at the repository root; its README is the manual, this page is where it
sits in the system.

## Boundaries

- **Outside the application.** `evals/` reads `backend/` and changes nothing in it; nothing in `backend/` or
  `frontend/` imports it, and there is no admin screen for it. Workers run with
  `uv run --project backend --frozen`, so the backend's lock file is untouched, with `PYTHONDONTWRITEBYTECODE=1`.
- **Hermetic configuration.** A worker is given the candidate's connection and models as the environment variables
  of `ai-providers.md`, with every ambient AI variable removed, `Settings(_env_file=None)` (no `.env`), and a
  database path that does not exist (the administrator's stored settings are never read). What a run measured is
  therefore the model in `models.toml`, not whatever the developer's shell held.
- **The real code.** The tutor suite drives the production `TutorService` through `scripts.probe`'s own cases and
  mechanical judges; the live suite is the provider test's live checks; the authoring suite is
  `scripts.authoring_eval`'s fixtures through the real `AuthoringAgent`. The harness adds one tap around the turn
  (time to first token, how it ended, usage, tool errors) and the aggregation.

## What a run produces

A folder `evals/results/<id>/` (gitignored): `run.json`, per model `live.json`, `tutor.json` (every trial with its
flags, timings, usage and transcript), `authoring.json` and the authoring outputs, the workers' logs, and
`report.md`. The report gives a **verdict per role** against the `[gates]` of `models.toml`, then the tutor table
(valid turns, board use, refused tool calls, answer leaks, out-of-pack formulas, French leaks, latency, tokens,
cost), the live checks, authoring, and, after `judge`, Claude's pairwise comparison with the reference.

## Cost

`models.toml` can give a model's prices (input, cached input, output; USD per million tokens). The report turns the
tokens a run measured into dollars per tutor turn and per authoring run, applying the prices in the file at the
time the report is built (by model name), so they can be added after a run. Two limits: cache-write charges are
not captured, and the probes repeat the same prompt prefix, so about 97% of input was served from the cache; it
is the cost of a warm session, not of a chapter's first turn.

Token counts per turn come from the tutor's `TurnEnd.usage`. Until spec 015's change (usage summed over the rounds of
a turn) that field held only the **last round's** usage, so runs measured before it understate tokens and cost per
turn by roughly half (the first comparison of 5 October); only runs made after it, or compared with each other, give
true per-turn cost. A run records whether the backend had uncommitted changes (`run.json`), but not which.

## The judge

`python -m harness judge` pairs each candidate turn with the reference's turn for the same case and trial (only
turns both finished cleanly), shows them in random order against a rubric that follows the product's invariants
(teach rather than tell, pack-only content, the moment, the voice), and records the winner and a reason. The score
counts ties as half, so 50% is parity; the report also gives how often the judge picked the answer shown first.
It uses the Anthropic API (`ANTHROPIC_API_KEY`), the one place the harness needs it, and costs money like the
runs themselves; both ask before spending.

## Limits

Screening, not a benchmark: 16 guardrail cases, a few runs each. The leak rate counts the answers the probes list.
Voice, transcription quality and the quality of an authored pack are not judged (the packs are saved to read).
The harness is coupled to the backend's `scripts/` and `TutorService`; `python -m harness plan` (free) and
`tests/backend/` catch a rename.

## Commands

```sh
cd evals && uv sync
uv run python -m harness plan                 # free
uv run python -m harness run                  # costs money
uv run python -m harness judge results/<run>  # costs money
uv run pytest -q                              # the pure parts
uv run --project ../backend --frozen pytest tests/backend -p no:cacheprovider -q
```
