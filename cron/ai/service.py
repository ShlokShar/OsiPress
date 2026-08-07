
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.shared_params import Reasoning

from cron.ai.prompts import (
    CLASSIFY_INSTRUCTIONS,
    SUMMARIZE_INSTRUCTIONS,
    TRANSLATE_INSTRUCTIONS
)
from cron.ai.schemas import (
    HeadlineClassifier,
    Parsed,
    TranslatedHeadline
)
from cron.ai.tools import (
    handle_iranian_date_text,
    handle_iranian_date_references,
)


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class AIService:
    def __init__(self, model: str = "gpt-5.4-nano",
                 translation_model: str = "gpt-5.6-luna"):
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.model = model
        self.translation_model = translation_model


    def classify(self, headline: str) -> bool:
        """
        Classifies if a headline is political at all. Used to filter out
        non-geopolitical articles (e.g. sports, celebrities, lifestyle, etc.)

        :param headline: the headline text which will be classified
        :return: True if the headline is political, False otherwise
        """

        if not headline:
            return False

        response = self.client.responses.parse(
            model=self.model,
            instructions=CLASSIFY_INSTRUCTIONS,
            input=f"Headline: {headline}",
            text_format=HeadlineClassifier
        )
        parsed = response.output_parsed
        if not parsed:
            return False

        return parsed.political

    def translate_headline(self, headline: str) -> str:
        """
        Translated the headline of the article into English. Uses Luna to
        translate the headline, rather than the default GPT-5.4-Nano.

        :param headline: the headline in its original language
        :return: the headline translated verbatim to English
        """

        if not headline:
            return "No headline found."

        response = self.client.responses.parse(
            model=self.translation_model,
            reasoning=Reasoning(effort="none"),
            instructions=TRANSLATE_INSTRUCTIONS,
            input=f"Headline: {headline}",
            text_format=TranslatedHeadline
        )

        parsed = response.output_parsed
        if not parsed:
            raise ValueError("No parsed translation.")
        dates = parsed.dates
        translated_headline = parsed.translated_headline

        translated_headline = handle_iranian_date_text(dates,
                                                       translated_headline)

        return translated_headline

    def summarize(self, headline: str, text: str) -> Optional[Parsed]:
        """
        Summarizes the summary of the article into English. Saves quotes that
        reference the article in its original language to back up the
        summary.

        :param headline: the original headline of the article
        :param text: the content of the article
        :return: the summary of the article and a list of references
        """

        if not text:
            return None

        response = self.client.responses.parse(
            model=self.model,
            instructions=SUMMARIZE_INSTRUCTIONS,
            input=f"Headline:\n{headline}\n\nArticle:\n{text}",
            text_format=Parsed
        )

        parsed = response.output_parsed
        if not parsed:
            return None
        summary = parsed.summary
        dates = parsed.dates

        parsed.summary = handle_iranian_date_text(dates, summary)

        for i, reference in enumerate(parsed.references_for_translation):
            dates = parsed.references_dates[i]
            try:
                parsed.references_for_translation[i] = (
                    handle_iranian_date_references(dates, reference)
                )
            except ValueError:
                parsed.references_for_translation[i] = parsed.references[i]

        return parsed

if __name__ == "__main__":
    ai_service = AIService()
    test_headline = "نشست خبری رئیس‌جمهور در ۳۰ تیر ۱۴۰۵ برگزار می‌شود"
    test_article = (
        "دولت اعلام کرد که نشست خبری رئیس‌جمهور در ۳۰ تیر ۱۴۰۵ برگزار "
        "شد و در آن برنامه‌های اقتصادی جدید کشور مورد بررسی قرار گرفت. "
        "سخنگوی دولت گفت مرحله نخست این برنامه در ۵ مرداد ۱۴۰۵ آغاز "
        "خواهد شد. بر اساس بیانیه رسمی، گزارش نتایج اولیه نیز در ۱۲ "
        "شهریور ۱۴۰۵ منتشر می‌شود."
    )
    translated_headline1 = ai_service.translate_headline(headline=test_headline)
    summary1 = ai_service.summarize(
        headline=test_headline,
        text=test_article,
    )
    print(translated_headline1)
    print(summary1)
