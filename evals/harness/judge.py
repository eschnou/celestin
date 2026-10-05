"""Pairwise judging of tutor turns: a candidate's answer against the reference's, by Claude.

Why pairwise: asking a model for "7 out of 10" on one answer is noisy and drifts with the judge's mood; asking
"which of these two is better, and why" is far steadier. Why against a reference: the question that decides a
model swap is "is it as good as what I run today", not "is it good".

Only turns where both models finished cleanly are judged (a turn that failed is already counted by the gates, and
judging it would only teach the judge what a missing answer looks like). The order is randomised per pair from a
seed, and the report says how often the judge picked whatever it was shown first.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

DEFAULT_JUDGE_MODEL = "claude-opus-5-5"
LANGUAGE_NAMES = {"fr": "French (French-speaking Belgium)", "en": "English"}


class Verdict(BaseModel):
    winner: Literal["A", "B", "tie"]
    reason: str


RUBRIC = """\
You compare two answers from an AI tutor, « Professor Célestin », for secondary-school students. The student \
brings the course material their teacher gave them; the tutor teaches from that material only. You will see the \
course pack (the tutor's only allowed source), the situation, and two candidate answers, A and B. Each answer is \
a transcript of one turn: what the tutor said, and the cards it put on the board (shown as JSON).

Decide which answer is the better tutor turn for this student in this situation. Judge on, in this order:

1. Teaching, not telling. While an exercise is open (see the situation), the answer must not hand over its \
solution or final value; hints should move the student one step. When the student only asks for the answer, \
the better turn holds the line kindly and still helps. Where no exercise is open, explaining is fine.
2. Fidelity to the pack. Definitions, formulas, notation, methods and vocabulary must come from the pack, in its \
notation. Anything the pack does not contain (a method it never teaches, a different notation) is a defect, \
even if correct elsewhere. Statements that are false are a worse defect.
3. Fit for the moment. It answers what the student actually said, follows the course path's rules when there \
is one (a locked section stays locked), and uses the board for structured content instead of dumping it in prose.
4. Voice. Clear, warm, short enough for a teenager to read; in the course language, with no stray language.

Do not reward length, formatting or confidence for their own sake. Do not let the order of A and B matter. \
Say « tie » only if the two are genuinely equivalent on these points. In `reason`, give one or two sentences \
that name the deciding difference and quote the words it rests on.
"""


def pack_block(language: str, title: str, pack: str) -> str:
    return f"Course language: {LANGUAGE_NAMES.get(language, language)}\n\n# Course pack — {title}\n\n{pack}"


def situation(case: dict[str, Any]) -> str:
    mode = (
        "parcours: the locked path of sections; the tutor teaches the section in progress"
        if case["mode"] == "parcours"
        else "discussion: a free conversation about the chapter, with no path and no progress"
    )
    prior = case["prior"].strip() or "(none: this is the start of the session)"
    message = case["message"].strip() or "(the student has said nothing yet: the tutor opens the session)"
    return f"Mode: {mode}\n\nConversation so far:\n{prior}\n\nThe student now says:\n{message}"


def user_prompt(case: dict[str, Any], a: str, b: str) -> str:
    return f"{situation(case)}\n\n<answer_a>\n{a}\n</answer_a>\n\n<answer_b>\n{b}\n</answer_b>"


Ask = Callable[[str, str, str], Verdict]  # (rubric, pack block, user prompt) -> verdict


def anthropic_ask(model: str) -> Ask:
    """A judge that calls Claude. The SDK is imported here so the rest of the harness never needs a key."""
    import anthropic

    client = anthropic.Anthropic()

    def ask(rubric: str, pack: str, prompt: str) -> Verdict:
        response = client.messages.parse(
            model=model,
            max_tokens=16000,
            # The pack is the long part and repeats for every pair of a chapter: cache it with the rubric.
            system=[
                {"type": "text", "text": rubric},
                {"type": "text", "text": pack, "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": prompt}],
            output_format=Verdict,
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise RuntimeError(f"the judge returned no verdict (stop_reason={response.stop_reason})")
        return response.parsed_output

    return ask


def load_tutor(run_dir: Path, name: str) -> dict[str, Any] | None:
    path = run_dir / name / "tutor.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def build_pairs(
    tutor: dict[str, dict[str, Any]], reference: str, seed: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """Every (candidate turn, reference turn) of the same case and trial that both ended cleanly, with the order
    each will be shown in. `limit` keeps an evenly spread subset, not the first cases."""
    ref_by_key = {(t["case"], t["trial"]): t for t in tutor[reference]["trials"] if t["ok"] and t["transcript"].strip()}
    pairs = []
    for name, data in tutor.items():
        if name == reference:
            continue
        for trial in data["trials"]:
            ref = ref_by_key.get((trial["case"], trial["trial"]))
            if ref is None or not trial["ok"] or not trial["transcript"].strip():
                continue
            first = random.Random(f"{seed}|{name}|{trial['case']}|{trial['trial']}").choice(["candidate", "reference"])
            pairs.append({"model": name, "case": trial["case"], "trial": trial["trial"], "first": first,
                          "candidate": trial["transcript"], "reference": ref["transcript"]})  # fmt: skip
    pairs.sort(key=lambda p: (p["model"], p["case"], p["trial"]))
    if limit is not None and limit < len(pairs):
        step = len(pairs) / limit
        pairs = [pairs[int(i * step)] for i in range(limit)]
    return pairs


def pair_key(pair: dict[str, Any]) -> tuple[str, str, int]:
    return pair["model"], pair["case"], pair["trial"]


def unjudged(pairs: list[dict[str, Any]], existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The pairs a previous judging did not decide. A pair that ended in `error` is tried again. Because the
    order of a pair comes from the run's seed, a pair judged earlier is the same pair now."""
    done = {pair_key(p) for p in existing if p["winner"] != "error"}
    return [p for p in pairs if pair_key(p) not in done]


def merge_judged(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Earlier verdicts plus the new ones; a new verdict replaces an older one for the same pair."""
    merged = {pair_key(p): p for p in existing}
    merged.update({pair_key(p): p for p in fresh})
    return sorted(merged.values(), key=pair_key)


def judge_pairs(
    tutor: dict[str, dict[str, Any]], pairs: list[dict[str, Any]], reference: str, ask: Ask, jobs: int = 4
) -> list[dict[str, Any]]:
    """Run the judge over the pairs. A failure is recorded as `error`, never raised: one bad call must not lose the rest."""

    def one(pair: dict[str, Any]) -> dict[str, Any]:
        data = tutor[pair["model"]]
        case = data["cases"][pair["case"]]
        packed = data["packs"][case["chapter"]]
        a, b = (pair["candidate"], pair["reference"]) if pair["first"] == "candidate" else (pair["reference"], pair["candidate"])
        result = {k: pair[k] for k in ("model", "case", "trial", "first")}
        try:
            verdict = ask(RUBRIC, pack_block(data["language"], packed["title"], packed["pack"]), user_prompt(case, a, b))
        except Exception as exc:  # noqa: BLE001
            return result | {"winner": "error", "reason": f"{type(exc).__name__}: {str(exc)[:160]}"}
        if verdict.winner == "tie":
            winner = "tie"
        else:
            shown_first = verdict.winner == "A"
            winner = pair["first"] if shown_first else ("reference" if pair["first"] == "candidate" else "candidate")
        return result | {"winner": winner, "reason": verdict.reason}

    # Pairs of one chapter next to each other, so the cached pack is read, not rewritten.
    ordered = sorted(pairs, key=lambda p: (tutor[p["model"]]["cases"][p["case"]]["chapter"], p["model"], p["case"], p["trial"]))
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(one, ordered))
