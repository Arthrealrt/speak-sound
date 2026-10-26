"""Bounded subtitle pages; the full transcript remains in history."""
import re


def subtitle_pages(text, measure, width, lines=2, max_pages=4):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    rows, row = [], ""
    # A broken recognizer must never create an unbounded GUI layout or queue.
    for char in text[:2000]:
        if row and measure(row + char) > width:
            rows.append(row.rstrip())
            row = ""
            if len(rows) >= lines * max_pages:
                rows[-1] = rows[-1].rstrip(".。… ") + "…"
                while len(rows[-1]) > 1 and measure(rows[-1]) > width:
                    rows[-1] = rows[-1][:-2] + "…"
                return ["\n".join(rows[i:i + lines]) for i in range(0, len(rows), lines)]
        row += char if row or not char.isspace() else ""
    if row:
        rows.append(row)
    if len(text) > 2000:
        rows[-1] = rows[-1][:-1] + "…"
    return ["\n".join(rows[i:i + lines]) for i in range(0, len(rows), lines)]
