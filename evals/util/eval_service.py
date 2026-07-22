
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import (
    BaseModel,
    Field
)


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class PredictionGrade(BaseModel):
    prediction: str = Field(description="an atomic claim made by the output")
    correct: bool = Field(description="whether the claim is supported by the "
                                      "provided source text")


class ReferenceGrade(BaseModel):
    reference: str = Field(description="a fact from the golden set")
    found: bool = Field(description="whether the output preserves this fact")


class PrecisionRecallGrade(BaseModel):
    predictions: list[PredictionGrade] = Field(description="the atomic claims "
                                                            "in the output")
    references: list[ReferenceGrade] = Field(description="the golden facts "
                                                          "checked for recall")


class EvalService:
    def __init__(self, model: str = "gpt-5.4-mini"):
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.model = model

    def grade_summary(self, article: str, summary: str,
                      expected_facts: list[str]) -> PrecisionRecallGrade:
        """
        Grades the factual precision and recall of an article summary.

        :param article: the original foreign-language article excerpt
        :param summary: the generated English summary
        :param expected_facts: the facts the golden summary should preserve
        :return: the individual claim and reference grades
        """

        response = self.client.responses.parse(
            model=self.model,
            instructions="You grade multilingual news summaries. Break the "
                         "generated summary into atomic factual claims. Mark "
                         "a claim correct only when it is supported by the "
                         "source excerpt. A less specific claim is correct "
                         "when the source entails it; score the omitted "
                         "detail only as a recall failure. Then check every "
                         "golden fact and "
                         "mark it found only when the generated summary "
                         "preserves it in English. Return exactly one "
                         "reference grade for every golden fact and copy the "
                         "golden fact into its reference field. Do not "
                         "require exact wording. A summary that is not in "
                         "English fails the task: mark its claims incorrect "
                         "and its golden facts not found. Do not give credit "
                         "for facts that appear only in the golden list but "
                         "are unsupported by the source.",
            input="Source excerpt:\n" + article +
                  "\n\nGenerated summary:\n" + summary +
                  "\n\nGolden facts:\n" + json.dumps(
                      expected_facts, ensure_ascii=False),
            text_format=PrecisionRecallGrade
        )

        return response.output_parsed

    def grade_translation(self, headline: str, translation: str,
                          reference: str,
                          meaning_units: list[str]) -> PrecisionRecallGrade:
        """
        Grades whether a headline translation is complete and verbatim.

        :param headline: the original foreign-language headline
        :param translation: the generated English translation
        :param reference: a human-reviewed reference translation
        :param meaning_units: the details the translation should preserve
        :return: the individual claim and reference grades
        """

        response = self.client.responses.parse(
            model=self.model,
            instructions="You grade English translations of foreign news "
                         "headlines. Verbatim means preserving every factual "
                         "detail, attribution, uncertainty, and charged term "
                         "without adding interpretation. Exact English word "
                         "order is not required. Accept reasonable phonetic "
                         "transliteration variants for personal and place "
                         "names when the intended person or place remains "
                         "clear. Do not accept translating a name into a "
                         "common noun, confusing it with another entity, or "
                         "dropping a title or factual descriptor. Require "
                         "established English names for named historical "
                         "events, institutions, programs, and systems. Be "
                         "strict about omitted facts, dates, gender, legal "
                         "or political concepts, and conventional terms. "
                         "Break the generated "
                         "translation into atomic meaning units. Mark each "
                         "unit correct only when supported by the original "
                         "headline. Then check whether every golden meaning "
                         "unit is preserved. Return exactly one reference "
                         "grade for every golden meaning unit and copy the "
                         "golden unit into its reference field. Use the "
                         "reference translation as guidance, not as the only "
                         "acceptable wording.",
            input="Original headline:\n" + headline +
                  "\n\nGenerated translation:\n" + translation +
                  "\n\nReference translation:\n" + reference +
                  "\n\nGolden meaning units:\n" + json.dumps(
                      meaning_units, ensure_ascii=False),
            text_format=PrecisionRecallGrade
        )

        return response.output_parsed
