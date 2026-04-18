"""
Flask app: upload PDF MCQs (yellow highlight = correct), merge into one bank, persist until reset.
"""

from __future__ import annotations

import json
import random
import secrets
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from pdf_quiz.parser import Question, parse_pdf, parse_pdf_bytes

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

DEFAULT_BANK_ID = "default"
_BANK_PATH = Path(__file__).resolve().parent / "data" / "bank.json"

# bank_id -> {"questions": list[Question], "meta": dict}
_BANKS: dict[str, dict] = {}
_QUIZ: dict[str, dict] = {}


def _ensure_data_dir() -> None:
    _BANK_PATH.parent.mkdir(parents=True, exist_ok=True)


def question_to_dict(q: Question) -> dict[str, Any]:
    return {
        "uid": q.uid,
        "number": q.number,
        "prompt": q.prompt,
        "options": q.options,
        "correct": q.correct,
        "week_hint": q.week_hint,
        "source": q.source,
    }


def question_from_dict(d: dict[str, Any]) -> Question:
    uid = d.get("uid") or uuid.uuid4().hex
    return Question(
        uid=uid,
        number=int(d["number"]),
        prompt=d["prompt"],
        options=d["options"],
        correct=d.get("correct"),
        week_hint=d.get("week_hint"),
        source=d.get("source"),
    )


def _bank_meta(questions: list[Question]) -> dict[str, Any]:
    sources: list[str] = []
    seen: set[str] = set()
    for q in questions:
        if q.source and q.source not in seen:
            seen.add(q.source)
            sources.append(q.source)
    weeks = sorted({q.week_hint for q in questions if q.week_hint is not None})
    return {
        "title": "Question bank",
        "total": len(questions),
        "sources": sources,
        "weeks_available": weeks,
    }


def _init_default_bank() -> None:
    if DEFAULT_BANK_ID not in _BANKS:
        _BANKS[DEFAULT_BANK_ID] = {"questions": [], "meta": _bank_meta([])}


def load_bank_from_disk() -> None:
    _init_default_bank()
    if not _BANK_PATH.is_file():
        return
    try:
        data = json.loads(_BANK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    qs = [question_from_dict(x) for x in data.get("questions", [])]
    _BANKS[DEFAULT_BANK_ID] = {"questions": qs, "meta": _bank_meta(qs)}


def save_bank_to_disk() -> None:
    _ensure_data_dir()
    qs = _BANKS.get(DEFAULT_BANK_ID, {}).get("questions", [])
    payload = {"questions": [question_to_dict(q) for q in qs]}
    _BANK_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _assign_uids(questions: list[Question]) -> None:
    for q in questions:
        if not q.uid:
            q.uid = uuid.uuid4().hex


def _merge_questions(new: list[Question]) -> None:
    _init_default_bank()
    _assign_uids(new)
    bank = _BANKS[DEFAULT_BANK_ID]
    bank["questions"].extend(new)
    bank["meta"] = _bank_meta(bank["questions"])
    save_bank_to_disk()


def _clear_bank() -> None:
    _BANKS[DEFAULT_BANK_ID] = {"questions": [], "meta": _bank_meta([])}
    if _BANK_PATH.is_file():
        try:
            _BANK_PATH.unlink()
        except OSError:
            pass


load_bank_from_disk()


def _q_public(q: Question) -> dict[str, Any]:
    return {
        "id": q.uid,
        "number": q.number,
        "prompt": q.prompt,
        "options": q.options,
        "source": q.source or "",
    }


def _serialize_session_row(q: Question, user_letter: str | None) -> dict[str, Any]:
    return {
        "id": q.uid,
        "number": q.number,
        "prompt": q.prompt,
        "options": q.options,
        "correct": q.correct,
        "user": user_letter,
        "is_correct": (user_letter == q.correct) if user_letter else False,
        "source": q.source or "",
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/quiz")
def quiz_page():
    return render_template("quiz.html")


@app.route("/api/state", methods=["GET"])
def api_state():
    _init_default_bank()
    bank = _BANKS[DEFAULT_BANK_ID]
    meta = bank["meta"]
    return jsonify(
        {
            "bank_id": DEFAULT_BANK_ID,
            "total": meta.get("total", 0),
            "sources": meta.get("sources", []),
            "weeks_available": meta.get("weeks_available", []),
            "title": meta.get("title", "Question bank"),
        }
    )


@app.route("/api/reset", methods=["POST"])
def api_reset():
    _clear_bank()
    return jsonify({"ok": True, "total": 0})


@app.route("/api/bank/<bid>", methods=["GET"])
def bank_detail(bid):
    if bid != DEFAULT_BANK_ID or bid not in _BANKS:
        return jsonify({"error": "Unknown bank"}), 404
    bank = _BANKS[bid]
    meta = bank["meta"]
    return jsonify(
        {
            "id": bid,
            "title": meta.get("title", "Question bank"),
            "total": meta.get("total", 0),
            "weeks_available": meta.get("weeks_available", []),
            "sources": meta.get("sources", []),
        }
    )


@app.route("/api/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file"}), 400
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "PDF only"}), 400
    data = f.read()
    if len(data) > 20 * 1024 * 1024:
        return jsonify({"error": "File too large (max 20MB)"}), 400
    try:
        questions, _meta = parse_pdf_bytes(data, f.filename)
    except Exception as e:
        return jsonify({"error": f"Could not parse PDF: {e!s}"}), 400
    if not questions:
        return jsonify({"error": "No questions found. Check yellow highlights and MCQ format."}), 400
    _merge_questions(questions)
    bank = _BANKS[DEFAULT_BANK_ID]
    return jsonify(
        {
            "bank_id": DEFAULT_BANK_ID,
            "added": len(questions),
            "total": bank["meta"]["total"],
            "source": f.filename,
            "sources": bank["meta"]["sources"],
            "title": bank["meta"]["title"],
        }
    )


@app.route("/api/load-example", methods=["POST"])
def load_example():
    p = Path.home() / "Downloads" / "Week 4.pdf"
    if not p.is_file():
        return jsonify({"error": "Example file not found at ~/Downloads/Week 4.pdf"}), 404
    questions, _meta = parse_pdf(p)
    if not questions:
        return jsonify({"error": "No questions parsed"}), 400
    for q in questions:
        q.source = p.name
    _merge_questions(questions)
    bank = _BANKS[DEFAULT_BANK_ID]
    return jsonify(
        {
            "bank_id": DEFAULT_BANK_ID,
            "added": len(questions),
            "total": bank["meta"]["total"],
            "source": p.name,
            "sources": bank["meta"]["sources"],
            "title": bank["meta"]["title"],
        }
    )


@app.route("/api/start", methods=["POST"])
def start_quiz():
    body = request.get_json(force=True, silent=True) or {}
    bank_id = body.get("bank_id") or DEFAULT_BANK_ID
    mode = body.get("mode", "quick")
    count = body.get("count")
    week = body.get("week")

    if bank_id not in _BANKS:
        return jsonify({"error": "No question bank. Upload PDFs first."}), 400

    pool: list[Question] = list(_BANKS[bank_id]["questions"])
    meta = _bank_meta(pool)

    if not pool:
        return jsonify({"error": "Question bank is empty. Upload PDFs or reset and add files."}), 400

    if mode == "week":
        try:
            wn = int(week)
        except (TypeError, ValueError):
            wn = None
        if wn is not None:
            filtered = [q for q in pool if q.week_hint == wn]
            if filtered:
                pool = filtered
        try:
            k = int(count) if count is not None else 10
        except (TypeError, ValueError):
            k = 10
        k = max(1, min(k, len(pool)))
    elif mode == "mock":
        k = len(pool)
    else:
        try:
            k = int(count) if count is not None else 10
        except (TypeError, ValueError):
            k = 10
        k = max(1, min(k, len(pool)))

    picked = random.sample(pool, k) if k < len(pool) else pool.copy()
    random.shuffle(picked)

    sid = uuid.uuid4().hex
    public = [_q_public(q) for q in picked]
    _QUIZ[sid] = {
        "bank_id": bank_id,
        "items": picked,
        "meta": meta,
        "mode": mode,
    }
    return jsonify(
        {
            "session_id": sid,
            "title": meta.get("title", "Quiz"),
            "mode": mode,
            "questions": public,
            "total": len(picked),
        }
    )


@app.route("/api/check", methods=["POST"])
def check_one():
    body = request.get_json(force=True, silent=True) or {}
    sid = body.get("session_id")
    qid = body.get("question_id")
    letter = body.get("answer")

    if not sid or sid not in _QUIZ:
        return jsonify({"error": "Invalid session"}), 400
    ul = str(letter).upper().strip() if letter is not None else ""
    if ul not in ("A", "B", "C", "D"):
        return jsonify({"error": "Bad answer"}), 400

    qid_s = str(qid)
    for q in _QUIZ[sid]["items"]:
        if q.uid == qid_s:
            return jsonify({"correct": ul == q.correct, "correct_letter": q.correct})
    return jsonify({"error": "Question not in session"}), 404


@app.route("/api/submit", methods=["POST"])
def submit():
    body = request.get_json(force=True, silent=True) or {}
    sid = body.get("session_id")
    answers = body.get("answers") or {}

    if not sid or sid not in _QUIZ:
        return jsonify({"error": "Invalid session"}), 400

    data = _QUIZ[sid]
    items: list[Question] = data["items"]
    meta = data["meta"]

    rows = []
    correct_n = 0
    for q in items:
        raw = answers.get(q.uid)
        if raw is None:
            raw = answers.get(str(q.number))
        ul = str(raw).upper().strip() if raw is not None else ""
        if ul not in ("A", "B", "C", "D"):
            ul = ""
        ok = ul == q.correct
        if ok:
            correct_n += 1
        rows.append(_serialize_session_row(q, ul if ul else None))

    total = len(items)
    return jsonify(
        {
            "title": meta.get("title", "Quiz"),
            "correct": correct_n,
            "total": total,
            "details": rows,
        }
    )


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)
