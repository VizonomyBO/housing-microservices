"""Language detection helpers backed by Lingua."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

try:
    from lingua import IsoCode639_1, Language, LanguageDetector, LanguageDetectorBuilder
except ImportError:  # pragma: no cover - lingual dependency may be optional during tests
    IsoCode639_1 = None  # type: ignore[assignment]
    Language = None  # type: ignore[assignment]
    LanguageDetector = None  # type: ignore[assignment]
    LanguageDetectorBuilder = None  # type: ignore[assignment]


@dataclass(frozen=True)
class LanguageDetectionResult:
    """Detection result including ISO-639-1 code and confidence."""

    language_code: str | None
    confidence: float | None


class LanguageDetectorProtocol(Protocol):
    """Protocol implemented by Lingua detectors and fakes in tests."""

    def detect(self, text: str) -> LanguageDetectionResult:  # pragma: no cover - interface
        """Return the detected language (if any)."""


class LinguaLanguageDetector:
    """Thin wrapper over lingua's LanguageDetector."""

    def __init__(self, languages: Sequence[str] | None = None) -> None:
        if LanguageDetectorBuilder is None:
            raise RuntimeError("lingua-language-detector is not installed")

        if languages:
            lingua_languages = []
            for code in languages:
                if not code:
                    continue
                resolved = None
                if hasattr(Language, "from_iso_code_639_1") and IsoCode639_1 is not None:
                    try:
                        iso_member = IsoCode639_1[code.upper()]
                    except KeyError:
                        iso_member = None
                    if iso_member is not None:
                        resolved = Language.from_iso_code_639_1(iso_member)
                if resolved is None:  # pragma: no cover - fallback for older lingua releases
                    try:
                        resolved = Language[code.upper()]
                    except KeyError:
                        resolved = None
                if resolved is not None:
                    lingua_languages.append(resolved)
            builder = LanguageDetectorBuilder.from_languages(*lingua_languages)
        else:
            builder = LanguageDetectorBuilder.from_all_languages()

        builder = builder.with_preloaded_language_models()
        low_memory = getattr(builder, "with_low_memory_mode", None)
        if callable(low_memory):
            builder = low_memory()
        self._detector = builder.build()

    def detect(self, text: str) -> LanguageDetectionResult:
        if not text or not text.strip():
            return LanguageDetectionResult(language_code=None, confidence=None)

        language = self._detector.detect_language_of(text)
        if language is None:
            return LanguageDetectionResult(language_code=None, confidence=None)

        confidence = self._detector.compute_language_confidence(text, language)
        code = language.iso_code_639_1.name.lower() if language.iso_code_639_1 else None
        return LanguageDetectionResult(language_code=code, confidence=confidence)


class StubLanguageDetector:
    """Trivial detector used in tests without pulling Lingua weights."""

    def __init__(self, language_code: str | None = None, confidence: float | None = None) -> None:
        self._language_code = language_code
        self._confidence = confidence

    def detect(self, text: str) -> LanguageDetectionResult:
        if not text or not text.strip():
            return LanguageDetectionResult(language_code=None, confidence=None)
        return LanguageDetectionResult(
            language_code=self._language_code, confidence=self._confidence
        )
