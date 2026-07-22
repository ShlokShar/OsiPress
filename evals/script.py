
import json
from datetime import (
    datetime,
    timezone
)
from pathlib import Path

from cron.util.ai_service import AIService
from evals.util.eval_service import EvalService


GOLDEN_SET_PATH = Path(__file__).resolve().parent / "golden_set.json"
RESULTS_PATH = (Path(__file__).resolve().parent /
                "results_luna_translation.json")


def get_metrics(true_positive: int, false_positive: int,
                false_negative: int) -> dict:
    """
    Calculates precision, recall, and F1 from the evaluation counts.

    :param true_positive: the number of correct positive predictions
    :param false_positive: the number of incorrect positive predictions
    :param false_negative: the number of missed positive references
    :return: a dictionary of evaluation metrics
    """

    precision_total = true_positive + false_positive
    recall_total = true_positive + false_negative
    precision = true_positive / precision_total if precision_total else 0
    recall = true_positive / recall_total if recall_total else 0
    f1_total = precision + recall
    f1 = 2 * precision * recall / f1_total if f1_total else 0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
    }


def evaluate_classifications(ai_service: AIService,
                             examples: list[dict]) -> dict:
    """
    Evaluates the political headline classifier against human labels.

    :param ai_service: the current production AI service
    :param examples: the classification examples from the golden set
    :return: the classification metrics and individual results
    """

    true_positive = 0
    false_positive = 0
    false_negative = 0
    true_negative = 0
    results = []

    for example in examples:
        prediction = ai_service.classify(example["headline"])
        expected = example["political"]

        if prediction and expected:
            true_positive += 1
        elif prediction and not expected:
            false_positive += 1
        elif not prediction and expected:
            false_negative += 1
        else:
            true_negative += 1

        results.append({
            "id": example["id"],
            "expected": expected,
            "prediction": prediction,
            "correct": prediction == expected,
        })

    metrics = get_metrics(true_positive, false_positive, false_negative)
    metrics["true_negative"] = true_negative
    metrics["accuracy"] = round(
        (true_positive + true_negative) / len(examples), 4
    ) if examples else 0

    return {
        "metrics": metrics,
        "examples": results,
    }


def evaluate_summaries(ai_service: AIService, eval_service: EvalService,
                       examples: list[dict]) -> dict:
    """
    Evaluates summary claims and golden fact coverage.

    :param ai_service: the current production AI service
    :param eval_service: the service used to grade open-ended outputs
    :param examples: the summary examples from the golden set
    :return: the summary metrics and individual results
    """

    correct_predictions = 0
    incorrect_predictions = 0
    found_references = 0
    missed_references = 0
    results = []

    for example in examples:
        processed = ai_service.summarize("", example["article"])
        summary = processed.summary if processed else ""
        grade = eval_service.grade_summary(
            example["article"], summary, example["expected_facts"]
        )

        correct_predictions += sum(
            prediction.correct for prediction in grade.predictions
        )
        incorrect_predictions += sum(
            not prediction.correct for prediction in grade.predictions
        )
        found_count = min(len(example["expected_facts"]), sum(
            reference.found for reference in grade.references
        ))
        found_references += found_count
        missed_references += len(example["expected_facts"]) - found_count

        results.append({
            "id": example["id"],
            "summary": summary,
            "predictions": [
                prediction.model_dump() for prediction in grade.predictions
            ],
            "references": [
                reference.model_dump() for reference in grade.references
            ],
        })

    precision_total = correct_predictions + incorrect_predictions
    recall_total = found_references + missed_references
    precision = correct_predictions / precision_total if precision_total else 0
    recall = found_references / recall_total if recall_total else 0
    f1_total = precision + recall
    f1 = 2 * precision * recall / f1_total if f1_total else 0

    return {
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "correct_claims": correct_predictions,
            "incorrect_claims": incorrect_predictions,
            "found_facts": found_references,
            "missed_facts": missed_references,
        },
        "examples": results,
    }


def evaluate_translations(ai_service: AIService, eval_service: EvalService,
                          examples: list[dict]) -> dict:
    """
    Evaluates headline translation meaning and completeness.

    :param ai_service: the current production AI service
    :param eval_service: the service used to grade open-ended outputs
    :param examples: the translation examples from the golden set
    :return: the translation metrics and individual results
    """

    correct_predictions = 0
    incorrect_predictions = 0
    found_references = 0
    missed_references = 0
    results = []

    for example in examples:
        processed = ai_service.translate_headline(example["headline"])
        translation = processed.translated_headline if processed else ""
        grade = eval_service.grade_translation(
            example["headline"], translation, example["reference"],
            example["meaning_units"]
        )

        correct_predictions += sum(
            prediction.correct for prediction in grade.predictions
        )
        incorrect_predictions += sum(
            not prediction.correct for prediction in grade.predictions
        )
        found_count = min(len(example["meaning_units"]), sum(
            reference.found for reference in grade.references
        ))
        found_references += found_count
        missed_references += len(example["meaning_units"]) - found_count

        results.append({
            "id": example["id"],
            "translation": translation,
            "predictions": [
                prediction.model_dump() for prediction in grade.predictions
            ],
            "references": [
                reference.model_dump() for reference in grade.references
            ],
        })

    precision_total = correct_predictions + incorrect_predictions
    recall_total = found_references + missed_references
    precision = correct_predictions / precision_total if precision_total else 0
    recall = found_references / recall_total if recall_total else 0
    f1_total = precision + recall
    f1 = 2 * precision * recall / f1_total if f1_total else 0

    return {
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "correct_units": correct_predictions,
            "incorrect_units": incorrect_predictions,
            "found_units": found_references,
            "missed_units": missed_references,
        },
        "examples": results,
    }


ai_service = AIService()
eval_service = EvalService()

with GOLDEN_SET_PATH.open("r", encoding="utf-8") as file:
    golden_set = json.load(file)

results = {
    "evaluated_at": datetime.now(timezone.utc).isoformat(),
    "production_model": ai_service.model,
    "judge_model": eval_service.model,
    "translation_model": ai_service.translation_model,
    "translation_method": "AIService.translate_headline",
    "translation_judge": "lenient name transliteration",
    "classification": evaluate_classifications(
        ai_service, golden_set["classifications"]
    ),
    "summary": evaluate_summaries(
        ai_service, eval_service, golden_set["summaries"]
    ),
    "translation": evaluate_translations(
        ai_service, eval_service, golden_set["translations"]
    ),
}

with RESULTS_PATH.open("w", encoding="utf-8") as file:
    json.dump(results, file, ensure_ascii=False, indent=2)

print("Classification:", results["classification"]["metrics"])
print("Summary:", results["summary"]["metrics"])
print("Translation:", results["translation"]["metrics"])
print("Detailed results:", RESULTS_PATH)
