"""Extras on top of mkdocs-llmstxt, which has no options for these."""

from pathlib import Path

# llms.txt section that is listed and gets per-page Markdown, but is left out of llms-full.txt;
# must be the last section in properdocs.yml, since page headings make section ends ambiguous
EXCLUDE_FROM_FULL = "Translations"


def on_page_context(context, page, config, nav):
    # llmstxt has converted the page by now; expose its Markdown URL to the template
    md_page = config.plugins["llmstxt"]._md_pages.get(page.file.src_uri)
    if md_page:
        page.meta["markdown_url"] = md_page.md_url
    return context


def on_post_build(config):
    # runs after llmstxt's own on_post_build, since hooks are registered after plugins
    full = Path(config.site_dir) / config.plugins["llmstxt"].config.full_output
    text = full.read_text(encoding="utf8")
    start = text.find(f"# {EXCLUDE_FROM_FULL}\n\n")
    if start >= 0:
        full.write_text(text[:start], encoding="utf8")
