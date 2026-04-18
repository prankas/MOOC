"""
Extract MCQs from PDFs where the correct option is marked with a yellow highlight
(vector fill rectangles). Also supports yellow over the answer text, not only the letter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz


@dataclass
class Question:
    number: int
    prompt: str
    options: dict[str, str]  # "A".."D" -> text without letter prefix
    correct: str | None  # "A".."D"
    week_hint: int | None = None
    uid: str = ""  # set by app when merging banks
    source: str | None = None  # original PDF filename


def _yellow_fill_rects(page: fitz.Page) -> list[fitz.Rect]:
    rects: list[fitz.Rect] = []
    for d in page.get_drawings():
        fill = d.get("fill")
        if not fill or len(fill) < 3:
            continue
        r, g, b = fill[0], fill[1], fill[2]
        if r > 0.85 and g > 0.85 and b < 0.25:
            rect = d.get("rect")
            if rect is not None:
                rects.append(rect)
    return rects


def _rects_intersect(a: fitz.Rect, b: fitz.Rect, pad: float = 1.0) -> bool:
    aa = fitz.Rect(a.x0 - pad, a.y0 - pad, a.x1 + pad, a.y1 + pad)
    return aa.intersects(b)


def _page_spans(page: fitz.Page) -> list[tuple[str, fitz.Rect]]:
    out: list[tuple[str, fitz.Rect]] = []
    d = page.get_text("dict")
    for b in d.get("blocks", []):
        if b.get("type") != 0:
            continue
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                t = span.get("text", "")
                if not t or not t.strip():
                    continue
                out.append((t, fitz.Rect(span["bbox"])))
    return out


_OPTION_START = re.compile(r"^\s*([a-dA-D])[\.\)]\s*")


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _letter_from_yellow(
    page: fitz.Page,
    yr: fitz.Rect,
    options: dict[str, str],
) -> str | None:
    spans = _page_spans(page)
    for text, rect in spans:
        if not _rects_intersect(rect, yr):
            continue
        t = text.strip()
        m = _OPTION_START.match(t)
        if m:
            return m.group(1).upper()
    # Highlight over answer body: find longest overlapping span and match to option text
    best: tuple[int, str] | None = None
    for text, rect in spans:
        if not _rects_intersect(rect, yr):
            continue
        if _OPTION_START.match(text.strip()):
            continue
        tl = text.strip()
        if len(tl) < 3:
            continue
        nt = _normalize(tl)
        for letter, body in options.items():
            nb = _normalize(body)
            if nb.startswith(nt[: min(len(nt), len(nb))]) or nt in nb or nb in nt:
                score = min(len(nt), len(nb))
                if best is None or score > best[0]:
                    best = (score, letter)
    return best[1] if best else None


def _question_starts(doc: fitz.Document) -> list[tuple[int, int, float]]:
    """(qnum, page_index, y0) for each question head 'N.' span."""
    out: list[tuple[int, int, float]] = []
    for pi in range(len(doc)):
        page = doc[pi]
        for text, rect in _page_spans(page):
            m = re.match(r"^(\d+)\.\s*$", text.strip())
            if not m:
                # Some source PDFs omit the space after the question marker (e.g. "8.What ...")
                m = re.match(r"^(\d+)\.\s*\S", text.strip())
            if m:
                out.append((int(m.group(1)), pi, rect.y0))
    out.sort(key=lambda x: (x[1], x[2]))
    return out


def _assign_yellow_to_question(
    starts: list[tuple[int, int, float]],
    page_index: int,
    y: float,
) -> int | None:
    """
    Map a yellow highlight to a question using **document order** (page, then y).

    Options that continue on the next page *before* the next question header (e.g. Q6
    options at the top of page 2) must map to the previous question — not the first
    question that starts on that page.
    """
    if not starts:
        return None
    yellow_pos = (page_index, y)
    sorted_starts = sorted(starts, key=lambda t: (t[1], t[2]))
    last_q: int | None = None
    for qnum, p, y0 in sorted_starts:
        if (p, y0) <= yellow_pos:
            last_q = qnum
    return last_q


def _strip_footers(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if re.match(r"^\s*--\s*\d+\s+of\s+\d+\s*--\s*$", line.strip()):
            continue
        lines.append(line)
    return "\n".join(lines)


_OPTION_LINE = re.compile(r"^\s*([a-dA-D])[\.\)]\s*(.*)$", re.DOTALL)


def _parse_block(num: int, body: str) -> tuple[str, dict[str, str]] | None:
    body = body.strip()
    lines = body.splitlines()
    prompt_parts: list[str] = []
    options: dict[str, str] = {}
    mode = "prompt"
    opt_order = ["A", "B", "C", "D"]

    for line in lines:
        m = _OPTION_LINE.match(line)
        if m:
            mode = "opts"
            letter = m.group(1).upper()
            rest = m.group(2).strip()
            if letter in opt_order:
                options[letter] = rest
        elif mode == "prompt":
            prompt_parts.append(line)
        else:
            if options:
                keys = [k for k in opt_order if k in options]
                last_key = keys[-1] if keys else None
                if last_key:
                    options[last_key] = (options[last_key] + " " + line).strip()

    prompt = " ".join(prompt_parts).strip()
    prompt = re.sub(r"\s+", " ", prompt)
    if len(options) < 2 or not prompt:
        return None
    return prompt, options


def parse_pdf(path: str | Path) -> tuple[list[Question], dict[str, Any]]:
    path = Path(path)
    doc = fitz.open(path)
    raw = _strip_footers("\n".join(doc[i].get_text() for i in range(len(doc))))
    starts_meta = _question_starts(doc)

    # Split raw text into question blocks
    # Accept both "8. Question" and "8.Question" styles.
    parts = re.split(r"(?m)^(?=\s*\d+\.\s*)", raw)
    blocks: list[tuple[int, str]] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        m = re.match(r"^\s*(\d+)\.\s*(.*)$", p, re.DOTALL)
        if not m:
            continue
        blocks.append((int(m.group(1)), m.group(2)))

    questions: list[Question] = []
    week_guess: int | None = None
    mwk = re.search(r"(?:Week|Assignment)\s*(\d+)", raw[:800], re.I)
    if mwk:
        week_guess = int(mwk.group(1))
    title = "Quiz"
    for line in raw.splitlines()[:10]:
        s = line.strip()
        if s and not re.match(r"^Assignment\s+\d+", s, re.I):
            title = s[:120]
            break

    # Build questions and fill correct from yellow using parsed options
    q_by_num: dict[int, Question] = {}
    for num, body in blocks:
        parsed = _parse_block(num, body)
        if not parsed:
            continue
        prompt, options = parsed
        q_by_num[num] = Question(
            number=num,
            prompt=prompt,
            options=options,
            correct=None,
            week_hint=week_guess,
            source=path.name,
        )

    for pi in range(len(doc)):
        page = doc[pi]
        for yr in _yellow_fill_rects(page):
            cy = (yr.y0 + yr.y1) / 2
            qn = _assign_yellow_to_question(starts_meta, pi, cy)
            if qn is None or qn not in q_by_num:
                continue
            q = q_by_num[qn]
            letter = _letter_from_yellow(page, yr, q.options)
            if letter:
                q.correct = letter

    for q in q_by_num.values():
        if q.correct and q.correct in q.options:
            questions.append(q)

    questions.sort(key=lambda x: x.number)
    doc.close()

    meta = {
        "title": title,
        "week": week_guess,
        "source": str(path.name),
    }
    return questions, meta


def parse_pdf_bytes(data: bytes, filename: str = "upload.pdf") -> tuple[list[Question], dict[str, Any]]:
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        p = f.name
    try:
        questions, meta = parse_pdf(p)
        for q in questions:
            q.source = filename
        meta["source"] = filename
        return questions, meta
    finally:
        Path(p).unlink(missing_ok=True)
