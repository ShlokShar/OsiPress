
import os
from pathlib import Path
from typing import (
    Optional,
    Literal,
    get_args
)

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import (
    BaseModel,
    Field
)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


ALLOWED_TAGS = Literal[
    "Conflict",
    "Diplomacy",
    "Sanctions",
    "Domestic",
    "Economy",
    "International",
]

class HeadlineClassifier(BaseModel):
    political: bool = Field(description="whether a headline is political")

class TranslatedHeadline(BaseModel):
    translated_headline: str = Field(description="headline translated verbatim "
                                                 "to English")

class Parsed(BaseModel):
    references: list[str] = Field(description="a list of quotes from the "
                                              "article that are used for the "
                                              "summary")
    tags: list[ALLOWED_TAGS] = Field(description="a list of tags from the "
                                                 "article")
    summary: str = Field(description="Summary of the article")

SUMMARIZE_INSTRUCTIONS = f"""You summarize political news articles written in \
foreign languages for an English-speaking reader.

Produce:
- summary: at most 3 sentences, written in English.
- references: short excerpts quoted exactly from the article in its original \
language that support the summary. Do not translate these.
- tags: every tag that applies, chosen only from: \
{", ".join(get_args(ALLOWED_TAGS))}

If the article cannot be summarized, set summary to 'This article cannot be \
summarized.' and leave references and tags empty."""


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
            instructions="""You classify RSS news headlines.
                            
                            Classify whether a headline is political if it's 
                            about:
                            - Politics
                            - Government policy
                            - Elections
                            - Diplomacy
                            - International relations
                            - Military affairs or conflict
                            - National security
                            - Sanctions
                            - Macroeconomics or economic policy
                            
                            Do not classify as political if the headline is 
                            primarily about:
                            - Sports
                            - Entertainment
                            - Celebrities
                            - Lifestyle
                            - Technology
                            - Science
                            - Health
                            - Weather""",
            input=f"Headline: {headline}",
            text_format=HeadlineClassifier
        )

        return response.output_parsed.political

    def translate_headline(self, headline: str) -> TranslatedHeadline:
        """
        Translated the headline of the article into English. Uses Luna to
        translate the headline, rather than the default GPT-5.4-Nano.

        :param headline: the headline in its original language
        :return: the headline translated verbatim to English
        """

        if not headline:
            return TranslatedHeadline(
                translated_headline="No headline found."
            )

        response = self.client.responses.parse(
            model=self.translation_model,
            reasoning={"effort": "none"},
            instructions="You translate foreign-language news headlines into "
                         "English. Produce a faithful, natural translation of "
                         "only the provided headline. Preserve every explicit "
                         "fact and relationship, including who did what to "
                         "whom, gender, number, titles, attribution, "
                         "uncertainty, dates, quotations, and suffix labels. "
                         "Use established English names for known people, "
                         "places, institutions, historical events, programs, "
                         "and systems. Do not translate proper names "
                         "literally. Reasonable transliteration variants are "
                         "acceptable when no established English form exists. "
                         "Do not paraphrase, summarize, editorialize, explain, "
                         "or add information. If the headline is already in "
                         "English, repeat it unchanged.",
            input=f"Headline: {headline}",
            text_format=TranslatedHeadline
        )

        return response.output_parsed

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

        return response.output_parsed
