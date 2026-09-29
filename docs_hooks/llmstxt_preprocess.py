"""Clean up page HTML before mkdocs-llmstxt converts it to Markdown."""

import re
from typing import Any

# pagetree macros are only expanded in the final HTML, after llmstxt has read the page
PAGETREE_MACRO = re.compile(r"^\s*\{\{\s*pagetree\(.*\)\s*\}\}\s*$")


def preprocess(soup: Any, output: str) -> None:
    for p in soup.find_all("p"):
        if PAGETREE_MACRO.match(p.get_text()):
            p.decompose()
