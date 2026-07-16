
import json
from pathlib import Path
from datetime import (
    datetime,
    timezone
)

import feedparser

from cron.util.ai_service import AIService
from cron.util.article import get_article_text, is_safe_article_url
from cron.util.log import add_log
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

try:
    ai_service = AIService()
except Exception as exception:
    add_log(
        f"AI service failed to initialize "
        f"({type(exception).__name__}): {exception}"
    )
    raise

run_time = datetime.now(timezone.utc)
try:
    with SOURCES_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)
except Exception as exception:
    add_log(
        f"Sources file failed to load "
        f"({type(exception).__name__}): {exception}"
    )
    raise

for country, sources in data.items():
    press_information = {} # for logging purposes

    # skip if country is not found in database
    try:
        country_object = Countries.get_country(country)
    except Exception as exception:
        add_log(
            f"{country}: failed to load country from database "
            f"({type(exception).__name__}): {exception}"
        )
        continue

    if not country_object:
        add_log(f"{country}: country is missing from database")
        continue

    # now iterate through the major sources for each country
    for source in sources:
        # if source does not exist in database, skip it.
        try:
            source_name = sources[source]["name"]
            url = sources[source]["url"]
        except (KeyError, TypeError) as exception:
            add_log(
                f"{country} / {source}: invalid source configuration "
                f"({type(exception).__name__}): {exception}"
            )
            continue

        try:
            source_object = Sources.get_source_by_name(country_object.id,
                                                       source_name)
        except Exception as exception:
            add_log(
                f"{country} / {source_name}: failed to load source from "
                f"database ({type(exception).__name__}): {exception}"
            )
            continue

        if not source_object:
            add_log(
                f"{country} / {source_name}: source is missing from database"
            )
            continue

        press_information[source] = {} # set the source

        try:
            feed = feedparser.parse(url) # parse the RSS
        except Exception as exception:
            add_log(
                f"{country} / {source_name}: feed failed to load "
                f"({type(exception).__name__}): {exception}"
            )
            continue

        feed_status = getattr(feed, "status", None)
        if feed_status != 200:
            add_log(
                f"{country} / {source_name}: feed returned status "
                f"{feed_status}"
            )
            continue

        if not feed.entries:
            add_log(f"{country} / {source_name}: feed returned no articles")
            continue

        saved_articles = 0

        # go through each object in the RSS
        for entry in feed.entries:
            headline = ""
            article = ""
            link = ""
            stage = "reading feed entry"
            try:
                # end iteration once there are enough articles recorded for this
                # source
                if len(press_information[source]) >= MAX_ARTICLES:
                    break

                headline = entry.title

                stage = "classifying headline"
                relevant = ai_service.classify(headline)

                stage = "reading article link"
                link = entry.link

                if not is_safe_article_url(link):
                    add_log(
                        f"{country} / {source_name} / {headline}: article "
                        f"URL failed the safety check ({link})"
                    )
                    continue

                # if this headline is not political at all, then skip
                if not relevant:
                    continue

                # get the article text and summarize it
                stage = "translating headline"
                translated_headline = translate(headline)

                stage = "extracting article text"
                article_text = get_article_text(link)
                if article_text == "empty article.":
                    add_log(
                        f"{country} / {source_name} / {headline}: article "
                        f"text extraction returned no text ({link})"
                    )

                stage = "summarizing article"
                processed_article = ai_service.summarize(article_text)

                # save the summary, references, and tags
                article_summary = processed_article.summary if (
                    processed_article) else "No summary provided."
                article_references = processed_article.references \
                    if processed_article else ["No references provided."]
                article_tags = processed_article.tags if processed_article \
                    else ["No tags provided."]

                stage = "translating references"
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
                    tags=article_tags,
                    captured_at=run_time,
                )

                stage = "saving article"
                Articles.add_article(article)
                saved_articles += 1
                print("tag:", article_tags)
            except Exception as exception:
                article_name = headline or "unknown headline"
                add_log(
                    f"{country} / {source_name} / {article_name}: {stage} "
                    f"failed ({type(exception).__name__}): {exception}"
                )
                print(exception)
                print(f"exception: {headline}: {article}")

        if saved_articles < MAX_ARTICLES:
            add_log(
                f"{country} / {source_name}: saved {saved_articles}/"
                f"{MAX_ARTICLES} articles"
            )
