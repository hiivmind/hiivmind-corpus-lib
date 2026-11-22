"""Table-row clean-up: sub-tables, packed cells, wrapped rows, empty columns, Markdown layout."""

from collections.abc import Sequence

from .emit import code_block, table

Row = Sequence[str | None]


def split_subtables(rows: Sequence[Row]) -> tuple[tuple[tuple[str | None, ...], ...], ...]:
    """Split on all-empty rows."""
    subtables: list[tuple[tuple[str | None, ...], ...]] = []
    current: list[tuple[str | None, ...]] = []
    for row in rows:
        if all(c is None or not c.strip() for c in row):
            if current:
                subtables.append(tuple(current))
                current = []
        else:
            current.append(tuple(row))
    if current:
        subtables.append(tuple(current))
    return tuple(subtables)


def expand_newline_cells(rows: Sequence[Row]) -> tuple[tuple[str, ...], ...]:
    """Turn newline-packed cells into columns, then pad every row to the widest."""
    expanded: list[list[str]] = []
    for row in rows:
        new_row: list[str] = []
        for cell in row:
            if cell and "\n" in cell:
                new_row.extend(part.strip() for part in cell.split("\n"))
            else:
                new_row.append(cell or "")
        expanded.append(new_row)
    width = max((len(r) for r in expanded), default=0)
    return tuple(tuple(r + [""] * (width - len(r))) for r in expanded)


def merge_continuation_rows(rows: Sequence[Row]) -> tuple[tuple[str, ...], ...]:
    """Fold wrapped rows into their parent; a sparse row (<=2 cells) merges forward into a fuller one."""
    merged: list[list[str]] = []
    for source in rows:
        row = [c or "" for c in source]
        if not merged:
            merged.append(row)
            continue
        first = next((i for i, c in enumerate(row) if c.strip()), None)
        if first is None:
            merged.append(row)
        elif first == 0:
            prev = merged[-1]
            if sum(1 for c in prev if c.strip()) <= 2 and sum(1 for c in row if c.strip()) > sum(1 for c in prev if c.strip()):
                for i, cell in enumerate(prev):
                    if i < len(row) and cell.strip() and not row[i].strip():
                        row[i] = cell.strip()
                merged[-1] = row
            else:
                merged.append(row)
        else:
            prev = merged[-1]
            for i, cell in enumerate(row):
                if i < len(prev) and cell.strip():
                    prev[i] = prev[i].rstrip() + " " + cell.strip() if prev[i].strip() else cell.strip()
    return tuple(tuple(r) for r in merged)


def strip_empty_columns(headers: Sequence[str], rows: Sequence[Sequence[str]]
                        ) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    keep = [i for i in range(len(headers))
            if any(v.strip() for v in [headers[i], *(row[i] for row in rows if i < len(row))])]
    if not keep:
        return tuple(headers), tuple(tuple(r) for r in rows)
    return (tuple(headers[i] for i in keep),
            tuple(tuple(row[i] for i in keep if i < len(row)) for row in rows))


def layout_table(rows: Sequence[Row]) -> str:
    """Markdown for raw extracted rows; sub-tables too sparse (over half empty) or wide (over 8 columns) become code blocks."""
    parts: list[str] = []
    for sub in split_subtables(rows):
        cleaned = [tuple((c or "").strip() for c in row) for row in sub]
        cleaned = merge_continuation_rows(cleaned)
        cleaned = merge_continuation_rows(expand_newline_cells(cleaned))
        headers, body = strip_empty_columns(cleaned[0], cleaned[1:])
        if not ("".join(headers) + "".join("".join(r) for r in body)).strip():
            continue
        total = len(headers) + sum(len(r) for r in body)
        empty = sum(1 for h in headers if not h.strip()) + sum(1 for r in body for c in r if not c.strip())
        if (total and empty / total > 0.5) or len(headers) > 8:
            lines = ["  ".join(c for c in row if c.strip()) for row in (headers, *body)]
            lines = [line for line in lines if line]
            if lines:
                parts += [code_block("\n".join(lines)), ""]
        else:
            parts += [table(headers, body), ""]
    return "\n".join(parts)
