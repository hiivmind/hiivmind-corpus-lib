"""Split a text into overlapping chunks at the best boundary near a token target."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from hiivmind_corpus_lib.markdown import headings
from hiivmind_corpus_lib.sections import Count, sections
from hiivmind_corpus_lib.tokens import count_tokens


class Strategy(StrEnum):
    MARKDOWN = "markdown"
    TRANSCRIPT = "transcript"
    CODE = "code"
    PARAGRAPH = "paragraph"
    HEADINGS = "headings"


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    line_start: int  # 1-based, inclusive
    line_end: int  # 1-based, inclusive
    overlap_previous: int
    heading_context: str | None


_TARGET, _OVERLAP = 900, 100
_CODE_TARGET, _CODE_OVERLAP = 600, 50
_ONE_CHUNK_FACTOR = 1.5
_MIN_WINDOW = 5
_UNIT_SPLIT_SCORE = 50  # the best score at which a unit-start boundary line starts the next chunk

_HEADING_SCORE, _BLANK_SCORE, _LIST_SCORE = 100, 20, 10
_SPEAKER_SCORE, _TIMESTAMP_SCORE = 80, 50
_CODE_SCORE = 100
_PARAGRAPH_BLANK_SCORE, _PARAGRAPH_LINE_SCORE = 50, 10

_LIST = re.compile(r"^\s*[-*+]\s|^\s*\d+\.\s")
_SPEAKER = re.compile(r"^[A-Z][a-zA-Z\s]*:\s")
_TIMESTAMP = re.compile(r"^\[?\d{1,2}:\d{2}(:\d{2})?\]?\s")
_CODE = re.compile(r"^(def |class |function |fn |func |pub fn |async fn |export |const \w+ = |let \w+ = )")


def _blank(line: str) -> bool:
    return not line.strip()


def _scorer(strategy: Strategy, text: str) -> tuple[Callable[[int, str], int], Callable[[int, str], bool]]:
    """(score, is_unit_start), each taking a 0-based line index and the line."""
    if strategy in (Strategy.MARKDOWN, Strategy.HEADINGS):
        heading_lines = {h.line - 1 for h in headings(text)}

        def score(i: int, line: str) -> int:
            if i in heading_lines:
                return _HEADING_SCORE
            if _blank(line):
                return _BLANK_SCORE
            return _LIST_SCORE if _LIST.match(line) else 0

        return score, lambda i, line: i in heading_lines
    if strategy is Strategy.TRANSCRIPT:
        def score(i: int, line: str) -> int:
            if _SPEAKER.match(line):
                return _SPEAKER_SCORE
            if _TIMESTAMP.match(line):
                return _TIMESTAMP_SCORE
            return _BLANK_SCORE if _blank(line) else 0

        return score, lambda i, line: bool(_SPEAKER.match(line) or _TIMESTAMP.match(line))
    if strategy is Strategy.CODE:
        def score(i: int, line: str) -> int:
            if _CODE.match(line):
                return _CODE_SCORE
            return _BLANK_SCORE if _blank(line) else 0

        return score, lambda i, line: bool(_CODE.match(line))

    def score(i: int, line: str) -> int:
        return _PARAGRAPH_BLANK_SCORE if _blank(line) else _PARAGRAPH_LINE_SCORE

    return score, lambda i, line: False


def _split(
    lines: list[str], lo: int, hi: int, score: Callable[[int, str], int], unit_start: Callable[[int, str], bool],
    target: int, overlap: int, count: Count,
) -> list[tuple[int, int]]:
    """Chunk the lines [lo, hi) into 0-based half-open ranges (overlap included)."""
    if lo >= hi:
        return []
    if count("\n".join(lines[lo:hi])) <= _ONE_CHUNK_FACTOR * target:
        return [(lo, hi)]
    cost = [1 if _blank(line) else count(line) for line in lines]
    result: list[tuple[int, int]] = []
    split, previous_start = lo, None
    while split < hi:
        taken, target_end = 0, None
        for i in range(split, hi):
            taken += cost[i]
            if taken >= target:
                target_end = i
                break
        if target_end is None or target_end == hi - 1:
            new_split = hi
        else:
            window = max(_MIN_WINDOW, (target_end - split) // 5)
            candidates = range(max(split + 1, target_end - window), min(hi - 1, target_end + window) + 1)
            # highest score; then nearest target_end; then the earlier
            boundary = min(candidates, key=lambda i: (-score(i, lines[i]), abs(i - target_end), i))
            best = score(boundary, lines[boundary])
            if best == 0:
                boundary = target_end
            new_split = boundary if best >= _UNIT_SPLIT_SCORE and unit_start(boundary, lines[boundary]) else boundary + 1
        start = split
        if previous_start is not None and overlap > 0:
            walked = 0
            while start - 1 > previous_start and walked < overlap:
                start -= 1
                walked += cost[start]
        result.append((start, new_split))
        previous_start = start
        split = new_split
    return result


def chunks(
    text: str,
    strategy: Strategy,
    *,
    target_tokens: int | None = None,
    overlap_tokens: int | None = None,
    count: Count = count_tokens,
) -> tuple[Chunk, ...]:
    if not text.strip():
        return ()
    code = strategy is Strategy.CODE
    target = target_tokens if target_tokens is not None else (_CODE_TARGET if code else _TARGET)
    overlap = overlap_tokens if overlap_tokens is not None else (_CODE_OVERLAP if code else _OVERLAP)
    lines = text.split("\n")
    score, unit_start = _scorer(strategy, text)

    def pieces(lo: int, hi: int) -> list[tuple[int, int]]:
        return _split(lines, lo, hi, score, unit_start, target, overlap, count)

    # (0-based start, 0-based end exclusive, heading context)
    ranges: list[tuple[int, int, str | None]] = []
    if strategy is Strategy.HEADINGS:
        found = sections(text, min_level=1, max_level=6, min_tokens=0, count=count)
        first = found[0].line_start - 1 if found else len(lines)
        ranges += [(a, b, None) for a, b in pieces(0, first)]
        stack: list[tuple[int, str]] = []
        for s in found:
            while stack and stack[-1][0] >= s.level:
                stack.pop()
            stack.append((s.level, s.title))
            context = " > ".join(title for _, title in stack)
            if s.tokens <= target:
                ranges.append((s.line_start - 1, s.line_end, context))
            else:
                ranges += [(a, b, context) for a, b in pieces(s.line_start - 1, s.line_end)]
    else:
        ranges = [(a, b, None) for a, b in pieces(0, len(lines))]

    result: list[Chunk] = []
    for a, b, context in ranges:
        body = lines[a:b]
        if all(_blank(line) for line in body):
            continue
        overlap_previous = max(0, result[-1].line_end - a) if result else 0
        result.append(Chunk(len(result), "\n".join(body), a + 1, b, overlap_previous, context))
    return tuple(result)
