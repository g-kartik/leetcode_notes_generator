import html
import re

from markdownify import MarkdownConverter


class LeetCodeMarkdownConverter(MarkdownConverter):
    """Custom Markdown converter tailored for LeetCode HTML structures."""

    def convert_sub(self, el, text, convert_as_inline):
        return f"_{text}"

    def convert_sup(self, el, text, convert_as_inline):
        return f"^{text}"

    def convert_pre(self, el, text, convert_as_inline):
        # Wraps example inputs/outputs in standard markdown code fences
        clean_code = text.strip()
        return f"\n```\n{clean_code}\n```\n"


def html_to_markdown(raw_html: str) -> str:
    """Converts LeetCode HTML description into clean Markdown."""
    if not raw_html:
        return ""

    try:
        unescaped = html.unescape(raw_html)
        converter = LeetCodeMarkdownConverter(
            heading_style="ATX",
            strip=["img", "script", "style"],
            bullets="-",
        )
        md = converter.convert(unescaped)

        # Post-processing: Remove excessive newlines (> 2 breaks)
        md = re.sub(r"\n{3,}", "\n\n", md)
        return md.strip()
    except Exception:
        return raw_html
