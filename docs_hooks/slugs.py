"""Heading anchor slugs matching GitHub, so README links work on the docs site."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from properdocs.config.defaults import ProperDocsConfig

RE_TAGS = re.compile(r"</?[^>]*>")


def github_slugify(text: str, sep: str) -> str:
    # unlike pymdownx.slugs, keep combining marks (e.g. Devanagari vowel signs) as GitHub does
    slug = unicodedata.normalize("NFC", RE_TAGS.sub("", text)).strip().lower()
    slug = "".join(c for c in slug if c in " -_" or unicodedata.category(c)[0] in "LMN")
    return slug.replace(" ", sep)


def on_config(config: ProperDocsConfig) -> ProperDocsConfig:
    config.mdx_configs.setdefault("toc", {})["slugify"] = github_slugify
    return config
