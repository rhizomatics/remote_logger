"""Extras on top of mkdocs-llmstxt, which has no options for these."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from properdocs.config.defaults import ProperDocsConfig
    from properdocs.structure.nav import Navigation
    from properdocs.structure.pages import Page
    from properdocs.utils.templates import TemplateContext

# llms.txt section that is listed and gets per-page Markdown, but is left out of llms-full.txt;
# must be the last section in properdocs.yml, since page headings make section ends ambiguous
EXCLUDE_FROM_FULL = "Translations"


def _llmstxt(config: ProperDocsConfig) -> Any:
    # the plugin's attributes aren't part of a typed API
    return cast("Any", config.plugins["llmstxt"])


def on_page_context(context: TemplateContext, page: Page, config: ProperDocsConfig, nav: Navigation) -> TemplateContext:
    # llmstxt has converted the page by now; expose its Markdown URL to the template
    md_page = _llmstxt(config)._md_pages.get(page.file.src_uri)
    if md_page:
        page.meta["markdown_url"] = md_page.md_url
    return context


def on_post_build(config: ProperDocsConfig) -> None:
    # runs after llmstxt's own on_post_build, since hooks are registered after plugins
    full = Path(config.site_dir) / _llmstxt(config).config.full_output
    text = full.read_text(encoding="utf8")
    start = text.find(f"# {EXCLUDE_FROM_FULL}\n\n")
    if start >= 0:
        full.write_text(text[:start], encoding="utf8")
