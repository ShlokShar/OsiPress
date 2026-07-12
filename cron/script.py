
import json
import traceback
from pathlib import Path
from datetime import (
    datetime,
    timezone
)

import feedparser

from cron.util.ai_service import AIService
from cron.util.article import get_article_text, is_safe_article_url
from cron.util.translation import (
    translate,
    translate_references
)
from shared.models import (
    Countries,
    Sources,
    Articles,
)


MAX_ARTICLES = 3
SOURCES_PATH = Path(__file__).resolve().parent / "sources.json"

ai_service = AIService()
run_time = datetime.now(timezone.utc)
with SOURCES_PATH.open("r", encoding="utf-8") as file:
    data = json.load(file)

for country, sources in data.items():
    press_information = {} # for logging purposes

    # skip if country is not found in database
    country_object = Countries.get_country(country)
    if not country_object:

        continue

    # now iterate through the major sources for each country
    for source in sources:
        # if source does not exist in database, skip it.
        source_name = sources[source]["name"]
        source_object = Sources.get_source_by_name(country_object.id,
                                                   source_name)
        if not source_object:
            continue

        press_information[source] = {} # set the source

        url = data[country][source]["url"]
        feed = feedparser.parse(url) # parse the RSS
        feed_status = getattr(feed, "status", None)
        if feed_status != 200:
            continue

        # go through each object in the RSS
        for entry in feed.entries:
            headline = ""
            article = ""
            try:
                # end iteration once there are enough articles recorded for this
                # source
                if len(press_information[source]) >= MAX_ARTICLES:
                    break

                headline = entry.title
                relevant = ai_service.classify(headline)
                link = entry.link

                if not is_safe_article_url(link):
                    continue

                # if this headline is not political at all, then skip
                if not relevant:
                    continue

                # get the article text and summarize it
                translated_headline = translate(headline)
                article_text = get_article_text(link)
                processed_article = ai_service.summarize(article_text)

                # save the summary and references
                article_summary = processed_article.summary if (
                    processed_article) else "No summary provided."
                article_references = processed_article.references \
                    if processed_article else ["No references provided."]

                references_translated = translate_references(article_references)

                press_information[source][headline] = {
                    article_summary: article_references
                }

                # save the article in the database with the timestamp
                article = Articles(
                    source_id=source_object.id,
                    headline=headline,
                    translated_headline=translated_headline,
                    link=link,
                    summary=article_summary,
                    references_original=article_references,
                    references_translated=references_translated,
                    captured_at=run_time,
                )
                Articles.add_article(article)
            except Exception:
                print(f"{headline}: {article}")
