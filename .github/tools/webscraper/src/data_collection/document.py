from __future__ import annotations

from dataclasses import dataclass

from selectolax.lexbor import LexborHTMLParser
from w3lib.encoding import html_to_unicode


@dataclass(frozen=True, slots=True)
class Document:
    html: str
    title: str
    text: str
    needs_browser: bool
    access_barrier: bool


def inspect_document(
    payload: bytes | str,
    content_type: str = "text/html",
    wait_selector: str | None = None,
) -> Document:
    html = payload if isinstance(payload, str) else html_to_unicode(content_type, payload)[1]
    tree = LexborHTMLParser(html)
    title_node = tree.css_first("title")
    title = title_node.text(strip=True) if title_node else ""
    has_scripts = tree.css_first("script") is not None
    selector_missing = wait_selector is not None and tree.css_first(wait_selector) is None
    for node in tree.css("script, style, noscript, template, svg, head"):
        node.decompose()
    text = " ".join(tree.text(separator=" ", strip=True).split())
    barrier_titles = {
        "access denied", "just a moment...", "attention required! | cloudflare",
        "verify you are human", "robot check", "security verification",
    }
    access_barrier = title.casefold().strip() in barrier_titles
    shell = has_scripts and (
        len(text) < 80
        or text.casefold() in {"loading...", "please enable javascript", "enable javascript to continue"}
    )
    return Document(html, title, text, selector_missing or shell or not text, access_barrier)