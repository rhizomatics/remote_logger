"""Heading anchor slugs matching GitHub, so README links work on the docs site."""

import re
import unicodedata

RE_TAGS = re.compile(r"</?[^>]*>")


def github_slugify(text: str, sep: str) -> str:
    # unlike pymdownx.slugs, keep combining marks (e.g. Devanagari vowel signs) as GitHub does
    slug = unicodedata.normalize("NFC", RE_TAGS.sub("", text)).strip().lower()
    slug = "".join(c for c in slug if c in " -_" or unicodedata.category(c)[0] in "LMN")
    return slug.replace(" ", sep)


def on_config(config):
    config.mdx_configs.setdefault("toc", {})["slugify"] = github_slugify
    return config
