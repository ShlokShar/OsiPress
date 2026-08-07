import argparse
import json
import re
import time
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
SOLAR_MONTH_NAMES = {
    "Farvardin", "Ordibehesht", "Khordad", "Tir", "Mordad", "Shahrivar",
    "Mehr", "Aban", "Azar", "Dey", "Bahman", "Esfand",
}


def example_category(example: dict) -> str:
    """Return an explicit category or infer one for legacy fixtures."""

    if "category" in example:
        return example["category"]
    if example.get("expected_summary_displays"):
        return "partial"
    if not example["expected_dates"]:
        return "negative"
    if any(
        0 in (date["year"], date["month"], date["day"])
        for date in example["expected_dates"]
    ):
        return "partial"
    return "full"


def expected_display(date: dict) -> str:
    """Return the user-visible value expected after deterministic formatting."""

    return date.get("display", date.get("gregorian", ""))


def contains_expected_display(text: str, display: str) -> bool:
    """Accept either natural order for a partial month-and-number date."""

    parts = display.split()
    variants = {display}
    if (
        len(parts) == 2
        and any(part in SOLAR_MONTH_NAMES for part in parts)
        and any(part.isdigit() for part in parts)
    ):
        variants.add(" ".join(reversed(parts)))

    return any(variant in text for variant in variants)


def validate_examples(document: dict) -> list[dict]:
    """Validate golden fixtures before making any paid model calls."""

    if document.get("category") != "dates":
        raise ValueError("golden document category must be 'dates'")

    examples = document.get("examples")
    if not isinstance(examples, list) or not examples:
        raise ValueError("golden document must contain at least one example")

    seen_ids = set()
    required_fields = {
        "id",
        "language",
        "headline",
        "article",
        "expected_dates",
    }

    for example in examples:
        missing_fields = required_fields - example.keys()
        if missing_fields:
            raise ValueError(
                f"{example.get('id', '<unknown>')} is missing fields: "
                f"{', '.join(sorted(missing_fields))}"
            )

        example_id = example["id"]
        if example_id in seen_ids:
            raise ValueError(f"duplicate example ID: {example_id}")
        seen_ids.add(example_id)

        if not example["headline"].strip() or not example["article"].strip():
            raise ValueError(f"{example_id} has empty input text")

        if not all(
            isinstance(display, str) and display
            for display in example.get("expected_summary_displays", [])
        ):
            raise ValueError(
                f"{example_id} has an invalid expected summary display"
            )

        for date in example["expected_dates"]:
            components = (date["year"], date["month"], date["day"])
            if not all(isinstance(component, int) for component in components):
                raise ValueError(f"{example_id} has non-integer date components")
            if not all(component > 0 for component in components):
                raise ValueError(
                    f"{example_id} contains an incomplete structured date"
                )

            formatted = convert_iranian_date(
                year=date["year"],
                month=date["month"],
                day=date["day"],
            )
            if formatted != expected_display(date):
                raise ValueError(
                    f"{example_id} expects {expected_display(date)!r}, but "
                    f"the deterministic formatter returns {formatted!r}"
                )

    return examples


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

    summary_started_at = time.perf_counter()
    processed = ai_service.summarize(
        example["headline"],
        example["article"],
    )
    summary_latency_ms = round(
        (time.perf_counter() - summary_started_at) * 1000,
        2,
    )
    if processed is None:
        return {
            "id": example["id"],
            "language": example["language"],
            "category": example_category(example),
            "passed": False,
            "error": "AIService.summarize returned None",
            "checks": {},
            "summary_latency_ms": summary_latency_ms,
            "headline_latency_ms": None,
        }

    expected_dates = expected_date_values(example)
    summary_dates = [serialize_date(date) for date in processed.dates]
    reference_dates = [
        serialize_date(date)
        for dates in processed.references_dates
        for date in dates
    ]
    expected_date_set = {
        (date["year"], date["month"], date["day"])
        for date in expected_dates
    }
    required_summary_date_set = {
        date
        for date in expected_date_set
        if all(component > 0 for component in date)
    }
    summary_date_set = {
        (date["year"], date["month"], date["day"])
        for date in summary_dates
    }
    reference_date_set = {
        (date["year"], date["month"], date["day"])
        for date in reference_dates
    }
    expected_converted_displays = [
        expected_display(date)
        for date in example["expected_dates"]
    ]
    expected_summary_displays = (
        expected_converted_displays
        + example.get("expected_summary_displays", [])
    )
    translated_references = processed.references_for_translation
    combined_translated_references = "\n".join(translated_references)
    translated_headline = None
    headline_latency_ms = None

    if "expected_headline_displays" in example:
        headline_started_at = time.perf_counter()
        translated_headline = ai_service.translate_headline(example["headline"])
        headline_latency_ms = round(
            (time.perf_counter() - headline_started_at) * 1000,
            2,
        )

    checks = {
        "summary_dates_are_allowed": summary_date_set <= expected_date_set,
        "summary_captures_full_dates": (
            required_summary_date_set <= summary_date_set
        ),
        "reference_dates_cover_expected": (
            reference_date_set == expected_date_set
        ),
        "reference_lists_aligned": (
            len(processed.references)
            == len(translated_references)
            == len(processed.references_dates)
        ),
        "references_present": bool(processed.references),
        "references_are_source_excerpts": all(
            reference in example["article"]
            for reference in processed.references
        ),
        "reference_copies_without_dates_unchanged": all(
            dates or original == translated
            for original, translated, dates in zip(
                processed.references,
                translated_references,
                processed.references_dates,
            )
        ),
        "no_unresolved_summary_placeholders": not PLACEHOLDER_PATTERN.search(
            processed.summary
        ),
        "no_unresolved_reference_placeholders": not PLACEHOLDER_PATTERN.search(
            combined_translated_references
        ),
        "summary_contains_expected_display_dates": all(
            contains_expected_display(processed.summary, date)
            for date in expected_summary_displays
        ),
        "references_contain_expected_display_dates": all(
            date in combined_translated_references
            for date in expected_converted_displays
        ),
        "reference_date_groups_match_text": all(
            all(
                convert_iranian_date(
                    month=date.month,
                    day=date.day,
                    year=date.year,
                )
                in reference
                for date in dates
            )
            for reference, dates in zip(
                translated_references,
                processed.references_dates,
            )
        ),
    }

    if translated_headline is not None:
        checks["headline_contains_expected_displays"] = all(
            contains_expected_display(translated_headline, display)
            for display in example["expected_headline_displays"]
        )
        checks["headline_has_no_unresolved_placeholder"] = (
            not PLACEHOLDER_PATTERN.search(translated_headline)
        )

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
        "category": example_category(example),
        "passed": all(checks.values()),
        "error": None,
        "checks": checks,
        "expected_dates": expected_dates,
        "summary_dates": summary_dates,
        "reference_dates": reference_dates,
        "summary": processed.summary,
        "translated_headline": translated_headline,
        "references": processed.references,
        "references_for_translation": translated_references,
        "summary_latency_ms": summary_latency_ms,
        "headline_latency_ms": headline_latency_ms,
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


def aggregate_results(results: list[dict], field: str) -> dict:
    """Aggregate pass counts by a result field such as category or language."""

    groups = {}
    for result in results:
        name = result[field]
        group = groups.setdefault(name, {"passed": 0, "failed": 0, "total": 0})
        group["total"] += 1
        if result["passed"]:
            group["passed"] += 1
        else:
            group["failed"] += 1

    for group in groups.values():
        group["accuracy"] = round(group["passed"] / group["total"], 4)

    return dict(sorted(groups.items()))


def main() -> int:
    """Run the multilingual date eval and print a compact report."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Run only the case with this ID; may be provided more than once.",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help="Run only this category; may be provided more than once.",
    )
    arguments = parser.parse_args()

    with GOLDEN_PATH.open("r", encoding="utf-8") as file:
        document = json.load(file)
    examples = validate_examples(document)

    if arguments.case:
        requested_ids = set(arguments.case)
        available_ids = {example["id"] for example in examples}
        unknown_ids = requested_ids - available_ids
        if unknown_ids:
            parser.error(
                f"unknown case IDs: {', '.join(sorted(unknown_ids))}"
            )
        examples = [
            example for example in examples
            if example["id"] in requested_ids
        ]

    if arguments.category:
        requested_categories = set(arguments.category)
        available_categories = {
            example_category(example) for example in examples
        }
        unknown_categories = requested_categories - available_categories
        if unknown_categories:
            parser.error(
                "unknown categories: "
                f"{', '.join(sorted(unknown_categories))}"
            )
        examples = [
            example for example in examples
            if example_category(example) in requested_categories
        ]

    ai_service = AIService()
    results = []
    for example in examples:
        started_at = time.perf_counter()
        try:
            result = evaluate_example(ai_service, example)
        except Exception as exception:
            result = {
                "id": example["id"],
                "language": example["language"],
                "category": example_category(example),
                "passed": False,
                "error": f"{type(exception).__name__}: {exception}",
                "checks": {},
                "summary_latency_ms": round(
                    (time.perf_counter() - started_at) * 1000,
                    2,
                ),
                "headline_latency_ms": None,
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
    failed = len(results) - passed
    total_latency_ms = round(sum(
        result["summary_latency_ms"]
        + (result["headline_latency_ms"] or 0)
        for result in results
    ), 2)
    run = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "dataset_version": document["version"],
            "production_model": ai_service.model,
            "translation_model": ai_service.translation_model,
            "method": "AIService.summarize",
            "case_ids": arguments.case or "all",
            "categories": arguments.category or "all",
            "summary_calls": len(examples),
            "headline_calls": sum(
                "expected_headline_displays" in example
                for example in examples
            ),
        },
        "metrics": {
            "passed": passed,
            "failed": failed,
            "total": len(results),
            "accuracy": round(passed / len(results), 4) if results else 0,
            "total_latency_ms": total_latency_ms,
            "average_latency_ms": (
                round(total_latency_ms / len(results), 2) if results else 0
            ),
            "by_category": aggregate_results(results, "category"),
            "by_language": aggregate_results(results, "language"),
        },
        "deployment_gate": {
            "passed": failed == 0,
            "blocking_failures": [
                result["id"] for result in results if not result["passed"]
            ],
        },
        "examples": results,
    }
    append_result(run)

    print("Metrics:", run["metrics"])
    print("Deployment gate:", run["deployment_gate"])
    print("Detailed results:", RESULTS_PATH)
    return 0 if run["deployment_gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
