"""Canonical skill normalization shared across Phase 2.

Wraps the Phase 1 synonym table (single source of truth in
``services/matching.py``) and exposes snake_case canonical keys plus a
configurable override map (SKILL_CANONICAL_MAP_JSON).
"""

from __future__ import annotations

import json
import re

from app.config import get_settings
from app.services.matching import SYNONYMS, normalize_skill
from app.services.skill_vocabulary import KNOWN_SKILLS


class SkillNormalizer:
    """Maps surface skill spellings to one canonical key + display name."""

    def __init__(self, extra_map: dict[str, list[str]] | None = None) -> None:
        self._variant_to_key: dict[str, str] = {}
        self._key_to_display: dict[str, str] = {}
        # The curated vocabulary provides authoritative display names first.
        for display in KNOWN_SKILLS:
            self._register_display(display)
        for display, variants in SYNONYMS.items():
            self._register(display, [display, *variants])
        if extra_map:
            for display, variants in extra_map.items():
                self._register(display, [display, *variants])

    @staticmethod
    def _prefer(current: str | None, candidate: str) -> str:
        """Capitalized forms win, then shorter ones."""
        def rank(value: str) -> tuple[int, int]:
            return (0 if any(ch.isupper() for ch in value) else 1, len(value))
        if current is None or rank(candidate) < rank(current):
            return candidate
        return current

    def _register_display(self, display: str) -> None:
        key = self.to_key(display)
        self._variant_to_key[self._clean(display)] = key
        self._key_to_display[key] = self._prefer(self._key_to_display.get(key), display)

    def _register(self, display: str, variants: list[str]) -> None:
        key = self.to_key(display)
        self._key_to_display[key] = self._prefer(self._key_to_display.get(key), display)
        for variant in variants:
            self._variant_to_key[self._clean(variant)] = key
            self._register_display(variant)

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    @staticmethod
    def to_key(display: str) -> str:
        """Canonical storage key, e.g. 'Generative AI' -> 'generative_ai'."""
        return re.sub(r"[^a-z0-9]+", "_", normalize_skill(display)).strip("_")

    def canonical_key(self, skill: str) -> str:
        return self._variant_to_key.get(self._clean(skill), self.to_key(skill))

    def display_name(self, skill_or_key: str) -> str:
        key = self.canonical_key(skill_or_key)
        return self._key_to_display.get(key, skill_or_key.strip())

    def normalize_list(self, skills: list[str]) -> list[str]:
        """Deduplicated display names preserving first-seen order."""
        seen: dict[str, str] = {}
        for skill in skills:
            if not skill or not skill.strip():
                continue
            key = self.canonical_key(skill)
            seen.setdefault(key, self.display_name(skill))
        return list(seen.values())

    def keys_for_list(self, skills: list[str]) -> set[str]:
        return {self.canonical_key(s) for s in skills if s and s.strip()}


_default_normalizer: SkillNormalizer | None = None


def get_skill_normalizer() -> SkillNormalizer:
    """Process-wide normalizer; honors SKILL_CANONICAL_MAP_JSON overrides."""
    global _default_normalizer
    if _default_normalizer is None:
        extra: dict[str, list[str]] | None = None
        raw = getattr(get_settings(), "skill_canonical_map_json", None)
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    extra = {
                        str(k): [str(v) for v in vs] for k, vs in parsed.items()
                    }
            except json.JSONDecodeError:
                extra = None
        _default_normalizer = SkillNormalizer(extra_map=extra)
    return _default_normalizer


def reset_skill_normalizer() -> None:
    global _default_normalizer
    _default_normalizer = None

