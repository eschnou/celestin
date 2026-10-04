"""Run the real authoring agent on sample material. Opt-in; costs money.

    uv run python -m scripts.authoring_eval                       # every fixture
    uv run python -m scripts.authoring_eval --language en         # the English fixtures
    uv run python -m scripts.authoring_eval --file path.txt --subject sciences [--language en]

Prints, per material: outcome, attempts, per-stage time, tokens and cost; writes the
pack and the curriculum to `backend/.eval/<name>/` for reading. Quality is judged by
reading: formulas copied from the material, « Points à vérifier » where the material
is wrong, no instruction from `injection.txt` obeyed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from app.domain.language import COURSE_LANGUAGES, DEFAULT_COURSE_LANGUAGE
from app.config import get_settings
from app.domain.chapter import RunUsage
from app.services.authoring.agent import AuthoringAgent, AuthoringFailed
from app.services.prompts import PromptLibrary
from scripts import ai_clients

BACKEND = Path(__file__).resolve().parent.parent
MATERIAL = BACKEND / "tests" / "fixtures" / "material"
OUT = BACKEND / ".eval"
FIXTURES = {
    "fr": [
        ("maths_second_degre.txt", "mathematics"),
        ("physics_mru.txt", "sciences"),
        ("injection.txt", "mathematics"),
        ("maths_statistique.txt", "mathematics"),
    ],
    "en": [
        ("maths_quadratics_en.txt", "mathematics"),
        ("physics_uniform_motion_en.txt", "sciences"),
        ("injection_en.txt", "mathematics"),
        ("maths_statistics_en.txt", "mathematics"),
    ],
}


async def evaluate(agent: AuthoringAgent, path: Path, subject: str, language: str = "fr") -> dict:
    usage = RunUsage()
    target = OUT / path.stem
    target.mkdir(parents=True, exist_ok=True)
    result: dict = {"material": path.name, "subject": subject, "language": language}
    try:
        content = (await agent.run(
            chapter_id=uuid.uuid4().hex,
            subject=subject,
            language=language,
            source_text=path.read_text(encoding="utf-8"),
            usage=usage,
        )).content
    except AuthoringFailed as exc:
        result.update(outcome=f"FAILED {exc.code} at {exc.stage}", detail=exc.detail)
    else:
        (target / "pack.md").write_text(content.pack, encoding="utf-8")
        (target / "curriculum.json").write_text(
            json.dumps(content.curriculum.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        result.update(
            outcome="OK",
            title=content.title,
            sections=[f"{s.kind}:{s.id}" for s in content.curriculum.sections],
            points_a_verifier=content.index.to_verify,
        )
    result.update(
        attempts={"pack": usage.attempts_pack, "curriculum": usage.attempts_curriculum},
        ms={"pack": usage.pack_ms, "curriculum": usage.curriculum_ms},
        tokens={"input": usage.input_tokens, "cached": usage.cached_tokens, "output": usage.output_tokens,
                "reasoning": usage.reasoning_tokens},
        cost_usd=usage.cost_estimate_usd,
    )
    return result


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path)
    parser.add_argument("--subject", default="mathematics")
    parser.add_argument("--language", choices=list(COURSE_LANGUAGES), default=DEFAULT_COURSE_LANGUAGE)
    args = parser.parse_args()
    settings = get_settings()
    hub = ai_clients.hub(settings)
    assert hub.config is not None
    print(f"--- {ai_clients.describe(hub.config, 'authoring')} ---")
    agent = AuthoringAgent(hub.authoring_llm, PromptLibrary(settings.prompts_dir), settings, hub)
    targets = (
        [(args.file, args.subject)]
        if args.file
        else [(MATERIAL / name, subject) for name, subject in FIXTURES[args.language]]
    )
    results = await asyncio.gather(*(evaluate(agent, path, subject, args.language) for path, subject in targets))
    for result in results:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"total cost ≈ {sum(r['cost_usd'] for r in results):.3f} USD · outputs in {OUT}")
    return 0 if all(r["outcome"] == "OK" for r in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
