"""Tests that all translation files match the structure of en.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent / "custom_components" / "remote_logger"
_TRANSLATIONS_DIR = _ROOT / "translations"
_ENGLISH = _TRANSLATIONS_DIR / "en.json"
_OTHER_TRANSLATIONS = sorted(p for p in _TRANSLATIONS_DIR.glob("*.json") if p != _ENGLISH)


def _all_key_paths(obj: object, prefix: str = "") -> set[str]:
    """Recursively collect every dot-separated key path in a nested dict."""
    if not isinstance(obj, dict):
        return {prefix} if prefix else set()
    paths: set[str] = set()
    for k, v in obj.items():
        child = f"{prefix}.{k}" if prefix else k
        paths |= _all_key_paths(v, child)
    return paths


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def english_keys() -> set[str]:
    return _all_key_paths(_load(_ENGLISH))


@pytest.fixture(scope="module")
def translation_files() -> list[Path]:
    return sorted(_TRANSLATIONS_DIR.glob("*.json"))


def test_at_least_one_translation_file(translation_files: list[Path]) -> None:
    assert translation_files, "No translation files found"


@pytest.mark.parametrize(
    "translation_path",
    _OTHER_TRANSLATIONS,
    ids=lambda p: p.stem,
)
def test_translation_has_all_english_keys(translation_path: Path, english_keys: set[str]) -> None:
    """Every key in en.json must be present in the translation file."""
    translation_keys = _all_key_paths(_load(translation_path))
    missing = english_keys - translation_keys
    assert not missing, f"{translation_path.name} is missing {len(missing)} key(s):\n" + "\n".join(
        f"  {k}" for k in sorted(missing)
    )


@pytest.mark.parametrize(
    "translation_path",
    _OTHER_TRANSLATIONS,
    ids=lambda p: p.stem,
)
def test_translation_has_no_extra_keys(translation_path: Path, english_keys: set[str]) -> None:
    """Translation files must not contain keys absent from en.json."""
    translation_keys = _all_key_paths(_load(translation_path))
    extra = translation_keys - english_keys
    assert not extra, f"{translation_path.name} has {len(extra)} extra key(s) not in en.json:\n" + "\n".join(
        f"  {k}" for k in sorted(extra)
    )
