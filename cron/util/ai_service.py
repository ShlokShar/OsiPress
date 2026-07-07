
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class HeadlineClassifier(BaseModel):
    political: bool = Field(description="whether a headline is political")

class Summarized(BaseModel):
    references: list[str] = Field(description="a list of quotes from the "
                                              "article that are used for the "
                                              "summary")
    summary: str = Field(description="Summary of the article")

class AIService:
    def __init__(self, model: str = "gpt-5.4-nano"):
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.model = model


    def classify(self, headline: str) -> bool:
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

    def summarize(self, text: str) -> Optional[Summarized]:
        response = self.client.responses.parse(
            model=self.model,
            instructions="You summarize political news articles from foreign "
                         "languages into English. The actual summary of the "
                         "article must be short and within 3 sentences. It's "
                         "important for you to have excerpts from the "
                         "original language that support your summary.",
            input=f"Article:\n {text}",
            text_format=Summarized
        )

        return response.output_parsed