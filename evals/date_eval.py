import json
import re
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path

from cron.ai.schemas import IranianDate
from cron.ai.service import AIService
from cron.ai.tools import convert_iranian_date


EVALS_DIR = Path(__file__).resolve().parent
GOLDEN_PATH = EVALS_DIR / "golden" / "dates.json"
RESULTS_PATH = EVALS_DIR / "results" / "dates.json"
PLACEHOLDER_PATTERN = re.compile(r"DATE_\d+")


def serialize_date(date: IranianDate) -> dict[str, int]:
    """Convert a parsed Solar Hijri date into a comparable dictionary."""

    return {
        "year": date.year,
        "month": date.month,
        "day": date.day,
    }


def expected_date_values(example: dict) -> list[dict[str, int]]:
    """Return expected Solar Hijri values without display-only fields."""

    return [
        {
            "year": date["year"],
            "month": date["month"],
            "day": date["day"],
        }
        for date in example["expected_dates"]
    ]


def evaluate_example(ai_service: AIService, example: dict) -> dict:
    """Run and deterministically grade one multilingual date example."""

    processed = ai_service.summarize(
        example["headline"],
        example["article"],
    )
    if processed is None:
        return {
            "id": example["id"],
            "language": example["language"],
            "passed": False,
            "error": "AIService.summarize returned None",
            "checks": {},
        }

    expected_dates = expected_date_values(example)
    summary_dates = [serialize_date(date) for date in processed.dates]
    reference_dates = [
        serialize_date(date)
        for dates in processed.references_dates
        for date in dates
    ]
    expected_gregorian = [
        date["gregorian"] for date in example["expected_dates"]
    ]
    translated_references = processed.references_for_translation
    combined_translated_references = "\n".join(translated_references)

    checks = {
        "summary_dates_exact": summary_dates == expected_dates,
        "reference_dates_exact": reference_dates == expected_dates,
        "reference_lists_aligned": (
            len(processed.references)
            == len(translated_references)
            == len(processed.references_dates)
        ),
        "references_are_source_excerpts": all(
            reference in example["article"]
            for reference in processed.references
        ),
        "no_unresolved_summary_placeholders": not PLACEHOLDER_PATTERN.search(
            processed.summary
        ),
        "no_unresolved_reference_placeholders": not PLACEHOLDER_PATTERN.search(
            combined_translated_references
        ),
        "summary_contains_expected_gregorian_dates": all(
            date in processed.summary for date in expected_gregorian
        ),
        "references_contain_expected_gregorian_dates": all(
            date in combined_translated_references
            for date in expected_gregorian
        ),
        "reference_date_groups_match_text": all(
            all(
                convert_iranian_date(date.year, date.month, date.day)
                in reference
                for date in dates
            )
            for reference, dates in zip(
                translated_references,
                processed.references_dates,
            )
        ),
    }

    if not expected_dates:
        checks["negative_case_has_no_reference_date_groups"] = all(
            not dates for dates in processed.references_dates
        )
        checks["negative_references_unchanged"] = (
            processed.references == translated_references
        )

    return {
        "id": example["id"],
        "language": example["language"],
        "passed": all(checks.values()),
        "error": None,
        "checks": checks,
        "expected_dates": expected_dates,
        "summary_dates": summary_dates,
        "reference_dates": reference_dates,
        "summary": processed.summary,
        "references": processed.references,
        "references_for_translation": translated_references,
    }


def append_result(run: dict) -> None:
    """Append a date-eval run to the ignored local results file."""

    if RESULTS_PATH.exists():
        with RESULTS_PATH.open("r", encoding="utf-8") as file:
            document = json.load(file)
    else:
        document = {"category": "dates", "runs": []}

    document["runs"].append(run)
    temporary_path = RESULTS_PATH.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(document, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary_path.replace(RESULTS_PATH)


def main() -> int:
    """Run the multilingual date eval and print a compact report."""

    with GOLDEN_PATH.open("r", encoding="utf-8") as file:
        examples = json.load(file)["examples"]

    ai_service = AIService()
    results = []
    for example in examples:
        try:
            result = evaluate_example(ai_service, example)
        except Exception as exception:
            result = {
                "id": example["id"],
                "language": example["language"],
                "passed": False,
                "error": f"{type(exception).__name__}: {exception}",
                "checks": {},
            }
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"{status}  {result['id']} ({result['language']})",
            flush=True,
        )
        for check, passed in result["checks"].items():
            if not passed:
                print(f"      failed: {check}", flush=True)
        if result["error"]:
            print(f"      error: {result['error']}", flush=True)

    passed = sum(result["passed"] for result in results)
    run = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "production_model": ai_service.model,
            "method": "AIService.summarize",
        },
        "metrics": {
            "passed": passed,
            "failed": len(results) - passed,
            "total": len(results),
            "accuracy": round(passed / len(results), 4) if results else 0,
        },
        "examples": results,
    }
    append_result(run)

    print("Metrics:", run["metrics"])
    print("Detailed results:", RESULTS_PATH)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
