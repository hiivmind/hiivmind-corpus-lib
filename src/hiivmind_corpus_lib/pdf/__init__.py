"""Pure PDF helpers: result types, Markdown emitters, cross-references, table rows, TeX math, outline chapters."""

from .chapters import chapters, chapters_by_font, chapters_from_outline
from .emit import (callout, chapter_markdown, code_block, dehyphenate, frontmatter, heading,
                   safe_file_name, table, wikilink)
from .rows import expand_newline_cells, layout_table, merge_continuation_rows, split_subtables, strip_empty_columns
from .reading import fonts, outline, page_count, strip_headers_footers, tables, text_blocks
from .split import split
from .texmath import decode_math, is_math_font
from .types import Box, Chapter, ChapterPdf, CrossRef, FontInfo, Manifest, TextBlock, TocEntry
from .xrefs import cross_references, resolve

__all__ = [
    "Box", "Chapter", "ChapterPdf", "CrossRef", "FontInfo", "Manifest", "TextBlock", "TocEntry",
    "callout", "chapter_markdown", "chapters_from_outline", "code_block", "cross_references", "decode_math",
    "dehyphenate", "expand_newline_cells", "frontmatter", "heading", "is_math_font", "layout_table",
    "merge_continuation_rows", "resolve", "safe_file_name", "split_subtables", "strip_empty_columns",
    "table", "wikilink",
    "chapters", "chapters_by_font", "fonts", "outline", "page_count", "split", "strip_headers_footers", "tables",
    "text_blocks",
]
