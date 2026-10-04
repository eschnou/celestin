"""Print the tool declarations exactly as the model receives them, per mode and course language."""

from __future__ import annotations

import json

from app.domain.language import COURSE_LANGUAGES
from app.domain.mode import MODES
from app.services.tools import registry

if __name__ == "__main__":
    for language in COURSE_LANGUAGES:
        for mode in MODES:
            declared = registry.declarations(mode, language)
            print(f"=== {mode} / {language} ({len(declared)} outils) ===")
            print(json.dumps(declared, indent=2, ensure_ascii=False))
