"""Reproducible 24-question development evaluation; never uses private workspace data."""

import argparse
import hashlib
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from app import rag, store

ROOT = Path(__file__).resolve().parent.parent


def evaluate(gemini=False, output=None):
    load_dotenv(ROOT / ".env")
    if gemini and not os.getenv("GEMINI_API_KEY", "").strip():
        raise SystemExit(
            "--gemini requires GEMINI_API_KEY. No generated-answer evaluation was run."
        )
    if not gemini:
        os.environ.pop(
            "GEMINI_API_KEY", None
        )  # Offline evaluation must never trigger paid API calls.
    questions_path = ROOT / "evaluation/questions.json"
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    rows = []
    original_data = os.getenv("DATA_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="margin-eval-") as directory:
            os.environ["DATA_DIR"] = directory
            store.initialize()
            for path in sorted((ROOT / "samples").glob("*.pdf")):
                content = path.read_bytes()
                chunks, pages = rag.chunks_from_pdf(content)
                store.add_document(
                    "evaluation",
                    str(uuid.uuid4()),
                    path.name,
                    content,
                    pages,
                    chunks,
                    rag.embed([c["text"] for c in chunks]),
                )
            chunks = store.get_chunks("evaluation", [])
            for question in questions:
                passages = rag.retrieve(question["question"], chunks)
                hit = any(
                    p["filename"] == question["expected_file"]
                    and p["page"] == question["expected_page"]
                    for p in passages
                )
                row = {
                    "id": question["id"],
                    "question": question["question"],
                    "expected_answerable": question["answerable"],
                    "expected_file": question["expected_file"],
                    "expected_page": question["expected_page"],
                    "retrieval_hit_at_5": hit if question["answerable"] else None,
                    "retrieved": [
                        {"file": p["filename"], "page": p["page"], "score": p["score"]}
                        for p in passages
                    ],
                }
                try:
                    result = rag.answer(question["question"], passages)
                    row.update(
                        {
                            "answer": result["answer"],
                            "answerable": result["answerable"],
                            "citations": result["citations"],
                        }
                    )
                    if gemini:
                        if question["answerable"]:
                            evidence = " ".join(c["quote"] for c in result["citations"])
                            row["generation_check_passed"] = bool(
                                result["answerable"]
                                and hit
                                and rag.normalize(question["expected_phrase"])
                                in rag.normalize(result["answer"] + " " + evidence)
                            )
                        else:
                            row["generation_check_passed"] = result["answerable"] is False
                    else:
                        row["generation_check_passed"] = None
                except RuntimeError as exc:
                    row.update(
                        {"error": str(exc), "generation_check_passed": False if gemini else None}
                    )
                rows.append(row)
                print(
                    f"{question['id']} | {'HIT' if hit else 'MISS' if question['answerable'] else 'UNKNOWN'} | {question['question']}"
                )
    finally:
        if original_data is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = original_data
    supported = [r for r in rows if r["expected_answerable"]]
    unknown = [r for r in rows if not r["expected_answerable"]]
    report = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "corpus": "Fictional Northstar development fixtures; not a held-out benchmark.",
        "dataset_sha256": hashlib.sha256(questions_path.read_bytes()).hexdigest(),
        "embedding_model": os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        "threshold": float(os.getenv("RETRIEVAL_THRESHOLD", "0.62")),
        "mode": "gemini" if gemini else "local-evidence",
        "generation_model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite") if gemini else None,
        "summary": {
            "questions": len(rows),
            "supported_questions": len(supported),
            "unanswerable_questions": len(unknown),
            "supported_retrieval_hits_at_5": sum(r["retrieval_hit_at_5"] for r in supported),
            "retrieval_recall_at_5": round(
                sum(r["retrieval_hit_at_5"] for r in supported) / len(supported), 4
            ),
            "unknown_questions_with_no_retrieval": sum(not r["retrieved"] for r in unknown),
            "generation_checks_passed": sum(r.get("generation_check_passed") is True for r in rows)
            if gemini
            else None,
            "generation_checks_run": len(rows) if gemini else 0,
        },
        "limitations": [
            "Local mode returns exact passages and does not decide semantic answerability when evidence is retrieved.",
            "Cosine similarity is not a confidence probability. A related passage may not answer the question.",
            "Generated checks use phrase matching plus source/page checks, not an independent factuality judge.",
            "Quotes and source IDs are validated; this does not prove that a generated claim follows from its quote.",
        ],
        "results": rows,
    }
    destination = Path(
        output or ROOT / ("evaluation/gemini-results.json" if gemini else "evaluation/results.json")
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], indent=2))
    print(f"Report: {destination}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gemini",
        action="store_true",
        help="Send fictional passages to Gemini and evaluate generated answers; may consume paid quota.",
    )
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()
    report = evaluate(args.gemini, args.output)
    if (
        report["summary"]["supported_retrieval_hits_at_5"]
        < report["summary"]["supported_questions"]
    ):
        raise SystemExit(1)
    if (
        args.gemini
        and report["summary"]["generation_checks_passed"] < report["summary"]["questions"]
    ):
        raise SystemExit(1)
