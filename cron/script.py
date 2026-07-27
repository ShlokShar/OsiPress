
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
    translate_references
)
from cron.util.search_service import SearchService
from shared.models import (
    Countries,
    Sources,
    Articles,
)


MAX_ARTICLES = 3
SOURCES_PATH = Path(__file__).resolve().parent / "sources.json"


try:
    ai_service = AIService()
    vector_service = SearchService()
except Exception as exception:
    add_log(
        f"AI or Vector Service failed to initialize "
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

    for source in sources:
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


        try:
            feed = feedparser.parse(url)
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

        for entry in feed.entries:
            headline = ""
            stage = "reading feed entry"
            try:
                if saved_articles >= MAX_ARTICLES:
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

                if not relevant:
                    continue

                stage = "extracting article text"
                article_text = get_article_text(link)
                if article_text == "empty article.":
                    add_log(
                        f"{country} / {source_name} / {headline}: article "
                        f"text extraction returned no text ({link})"
                    )

                stage = "translating headline"
                translated_result = ai_service.translate_headline(headline)

                translated_headline = (
                    translated_result.translated_headline
                    if translated_result
                    else "No headline translated."
                )

                stage = "summarizing article"
                processed_article = ai_service.summarize(headline, article_text)

                article_summary = processed_article.summary if (
                    processed_article) else "No summary provided."
                article_references = processed_article.references \
                    if processed_article else ["No references provided."]
                article_tags = processed_article.tags if processed_article \
                    else ["No tags provided."]

                stage = "translating references"
                references_translated = translate_references(article_references)


                stage = "embedding article"

                article_overview = f"{translated_headline}:{article_summary}"

                try:
                    vector = vector_service.embed(article_overview)
                except Exception as exception:
                    add_log(
                        f"exception: {type(exception).__name__}: {exception}"
                        f"failed to embed article overview: {article_overview}"
                    )
                    vector = None

                article = Articles(
                    source_id=source_object.id,
                    headline=headline,
                    translated_headline=translated_headline,
                    link=link,
                    summary=article_summary,
                    references_original=article_references,
                    references_translated=references_translated,
                    tags=article_tags,
                    embedding=vector,
                    captured_at=run_time,
                )

                stage = "saving article"
                Articles.add_article(article)
                saved_articles += 1
            except Exception as exception:
                article_name = headline or "unknown headline"
                add_log(
                    f"{country} / {source_name} / {article_name}: {stage} "
                    f"failed ({type(exception).__name__}): {exception}"
                )

        if saved_articles < MAX_ARTICLES:
            add_log(
                f"{country} / {source_name}: saved {saved_articles}/"
                f"{MAX_ARTICLES} articles"
            )
