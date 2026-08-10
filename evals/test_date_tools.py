import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from cron.ai.schemas import IranianDate
from cron.ai.tools import (
    convert_iranian_date,
    handle_iranian_date_references,
    handle_iranian_date_text,
)
from evals.date_eval import (
    aggregate_results,
    contains_expected_display,
    example_category,
    validate_examples,
)


GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "dates.json"


class IranianDateConversionTests(unittest.TestCase):
    def test_complete_date_converts_to_gregorian(self):
        self.assertEqual(
            convert_iranian_date(month=4, day=3, year=1405),
            "June 24, 2026",
        )

    def test_leap_day_converts_to_gregorian(self):
        self.assertEqual(
            convert_iranian_date(month=12, day=30, year=1399),
            "March 20, 2021",
        )

    def test_zero_year_is_rejected_by_schema(self):
        with self.assertRaises(ValidationError):
            IranianDate(year=0, month=4, day=3)

    def test_zero_day_is_rejected_by_schema(self):
        with self.assertRaises(ValidationError):
            IranianDate(year=1405, month=4, day=0)

    def test_impossible_month_day_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "day must be in 1..30"):
            convert_iranian_date(year=1405, month=7, day=31)

    def test_non_leap_esfand_day_is_rejected(self):
        with self.assertRaises(ValueError):
            convert_iranian_date(month=12, day=30, year=1400)


class DatePlaceholderTests(unittest.TestCase):
    def test_text_placeholders_are_replaced_by_exact_index(self):
        dates = [
            IranianDate(year=1405, month=4, day=3),
            IranianDate(year=1405, month=5, day=5),
        ]

        result = handle_iranian_date_text(
            dates,
            "The meetings are on DATE_0 and DATE_1.",
        )

        self.assertEqual(
            result,
            "The meetings are on June 24, 2026 and July 27, 2026.",
        )

    def test_text_without_dates_or_placeholders_is_unchanged(self):
        text = "No Solar Hijri date appears here."
        self.assertEqual(handle_iranian_date_text([], text), text)

    def test_text_date_without_placeholder_is_rejected(self):
        dates = [IranianDate(year=1405, month=4, day=3)]
        with self.assertRaisesRegex(ValueError, "Expected placeholders"):
            handle_iranian_date_text(dates, "The meeting is on 3 Tir 1405.")

    def test_text_placeholder_without_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Expected placeholders"):
            handle_iranian_date_text([], "The meeting is on DATE_0.")

    def test_text_out_of_order_placeholders_are_rejected(self):
        dates = [
            IranianDate(year=1405, month=4, day=3),
            IranianDate(year=1405, month=5, day=5),
        ]
        with self.assertRaisesRegex(ValueError, "Expected placeholders"):
            handle_iranian_date_text(dates, "DATE_1 then DATE_0")

    def test_reference_replacement_uses_occurrence_order(self):
        dates = [
            IranianDate(year=1405, month=4, day=3),
            IranianDate(year=1405, month=5, day=5),
        ]

        result = handle_iranian_date_references(
            dates,
            "نخست DATE_7 و سپس DATE_12 اعلام شد.",
        )

        self.assertEqual(
            result,
            "نخست June 24, 2026 و سپس July 27, 2026 اعلام شد.",
        )

    def test_reference_placeholder_mismatch_is_rejected(self):
        dates = [IranianDate(year=1405, month=4, day=3)]
        with self.assertRaisesRegex(ValueError, "2 date placeholders"):
            handle_iranian_date_references(dates, "DATE_0 and DATE_1")

    def test_placeholder_like_substrings_are_not_replaced(self):
        text = "PREDATE_0 and DATE_0_SUFFIX are ordinary text."
        self.assertEqual(handle_iranian_date_text([], text), text)


class DateEvalInfrastructureTests(unittest.TestCase):
    def test_partial_date_display_accepts_both_natural_orders(self):
        self.assertTrue(contains_expected_display("on 3 Tir", "Tir 3"))
        self.assertTrue(contains_expected_display("in Tir 1405", "Tir 1405"))

    def test_production_golden_set_is_valid_and_broad(self):
        with GOLDEN_PATH.open("r", encoding="utf-8") as file:
            document = json.load(file)

        examples = validate_examples(document)
        languages = {example["language"] for example in examples}
        categories = {example_category(example) for example in examples}

        self.assertGreaterEqual(len(examples), 60)
        self.assertEqual(languages, {"Persian", "English", "Hebrew"})
        self.assertGreaterEqual(len(categories), 8)

    def test_result_aggregation_reports_failures(self):
        results = [
            {"category": "full", "passed": True},
            {"category": "full", "passed": False},
            {"category": "partial", "passed": True},
        ]

        aggregate = aggregate_results(results, "category")

        self.assertEqual(
            aggregate["full"],
            {"passed": 1, "failed": 1, "total": 2, "accuracy": 0.5},
        )
        self.assertEqual(aggregate["partial"]["accuracy"], 1.0)

if __name__ == "__main__":
    unittest.main()
