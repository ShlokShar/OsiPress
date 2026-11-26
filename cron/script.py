
import json
import heapq
import os
import time
from datetime import (
    datetime,
    timezone
)
from pathlib import Path
from types import SimpleNamespace
from typing import (
    Optional,
    TypedDict,
)

import feedparser
import requests
from feedparser.util import FeedParserDict
from sqlalchemy import func, tuple_

from cron.ai.service import AIService
from cron.events.cluster import EventClusterer, ReplayArticle
from cron.events.config import EVENTS_COLLECTION
from cron.events.vector_store import EventVectorStore
from cron.util.article import (
    get_article_content,
    is_safe_article_url
)
from cron.util.backfill_vectors import upsert_article
from cron.util.log import add_log
from cron.util.translation import (
    translate_references
)
from cron.util.url import normalize_article_url, normalize_item_guid
from shared.database import SessionLocal
from shared.models import (
    Articles,
    ArticleAppearances,
    ArticleEvents,
    Countries,
    OutletRunLog,
    PendingItem,
    Sources,
    add_outlet_token_usage,
    add_canonical_article,
    complete_ingestion_run,
    fail_ingestion_run,
    find_article_by_url,
    complete_pending_item,
    get_seen_items,
    get_pending_items,
    get_feed_pending,
    queue_item,
    mark_pending_political,
    mark_item_seen,
    save_outlet_run_log,
    stage_appearance,
    stage_pending_item,
    start_ingestion_run,
)
from shared.search_service import SearchService


class SourceConfig(TypedDict, total=False):
    name: str
    url: str
    rss: bool


SourcesData = dict[str, dict[str, SourceConfig]]
SetupResult = tuple[AIService, SearchService, datetime, SourcesData]
SourceResult = tuple[Sources, str, str]
ArticleInfo = tuple[
    str,
    str,
    str,
    str,
    list[str],
    list[str],
    list[str],
    Optional[list[float]],
    Optional[datetime],
    dict,
]


MAX_ITEMS_PER_OUTLET_PER_RUN = int(os.getenv("MAX_ITEMS_PER_OUTLET_PER_RUN", "25"))
SOURCES_PATH = Path(__file__).resolve().parent / "sources.json"
FEED_TIMEOUT = (5, 20)
FEED_ATTEMPTS = 2
EVENT_CLUSTERING_ENABLED = os.getenv("EVENT_CLUSTERING_ENABLED") == "1"


def setup() -> SetupResult:
    """
    Initiates and declares the ai_service and vector_service. Opens the JSON
    file and saves it as data and sets the run time for the script.

    :return: the ai_service and vector_service instances, run_time and data
    variables
    """

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

    return ai_service, vector_service, run_time, data


def get_country(country: str) -> Optional[Countries]:
    """
    Finds the country object in the database from the name in the JSON data.

    :param country: the country name as per the JSON data
    :return: the matching country database object, or None if not found
    """

    try:
        country_object = Countries.get_country(country)
    except Exception as exception:
        add_log(
            f"{country}: failed to load country from database "
            f"({type(exception).__name__}): {exception}"
        )
        return None

    if not country_object:
        add_log(f"{country}: country is missing from database")
        return None
    return country_object


def get_source(
    country_object: Countries,
    country: str,
    source: str,
    config: SourceConfig,
) -> Optional[SourceResult]:
    """
    Gets the source object from the database based on the country name.

    :param country_object: the country object from the database
    :param country: the country name as per the JSON data
    :param source: the source name as per the JSON data
    :param config: the SourceConfig instance
    :return: the source object, or None if not found
    """

    try:
        source_name = config["name"]
        url = config["url"]
    except (KeyError, TypeError) as exception:
        add_log(
            f"{country} / {source}: invalid source configuration "
            f"({type(exception).__name__}): {exception}"
        )
        return None

    try:
        source_object = Sources.get_source_by_name(
            country_object.id,
            source_name
        )
    except Exception as exception:
        add_log(
            f"{country} / {source_name}: failed to load source from "
            f"database ({type(exception).__name__}): {exception}"
        )
        return None

    if not source_object:
        add_log(
            f"{country} / {source_name}: source is missing from database"
        )
        return None

    return source_object, source_name, url


def validate_feed(
    url: str,
    country: str,
    source_name: str,
) -> Optional[FeedParserDict]:
    """
    Gets the feed information and checks if the request / response was valid.

    :param url: the RSS feed URL
    :param country: the country name as per the JSON data
    :param source_name: the source name as per the JSON data
    :return: the feed object, or None if not found
    """

    for attempt in range(1, FEED_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "OsiPress/1.0"},
                timeout=FEED_TIMEOUT,
            )
        except requests.RequestException as exception:
            if attempt == FEED_ATTEMPTS:
                add_log(
                    f"{country} / {source_name}: feed failed to load "
                    f"({type(exception).__name__}): {exception}"
                )
                return None
            add_log(
                f"{country} / {source_name}: feed request failed; retrying "
                f"({type(exception).__name__}): {exception}"
            )
            time.sleep(1)
            continue

        try:
            if response.status_code == 200:
                try:
                    feed = feedparser.parse(response.content)
                except Exception as exception:
                    add_log(
                        f"{country} / {source_name}: feed failed to parse "
                        f"({type(exception).__name__}): {exception}"
                    )
                    return None
                break

            if response.status_code < 500 or attempt == FEED_ATTEMPTS:
                add_log(
                    f"{country} / {source_name}: feed returned status "
                    f"{response.status_code}"
                )
                return None

            add_log(
                f"{country} / {source_name}: feed returned status "
                f"{response.status_code}; retrying"
            )
        finally:
            response.close()

        time.sleep(1)

    if not feed.entries:
        add_log(f"{country} / {source_name}: feed returned no articles")
    return feed


def item_published_at(entry: FeedParserDict) -> Optional[datetime]:
    published = getattr(entry, "published_parsed", None)
    if not published:
        return None
    try:
        return datetime(*published[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def get_article_info(
    entry: FeedParserDict,
    ai_service: AIService,
    vector_service: SearchService,
    already_classified: bool = False,
) -> Optional[ArticleInfo]:
    """
    Retrieves all the information needed to create an article instance,
    including the article vector.

    :param entry: the RSS feed entry to process
    :param ai_service: the service used to classify and process article text
    :param vector_service: the service used to embed the article overview
    :return: the processed article information, or None if processing fails
    """

    headline = "Unknown headline"
    try:
        headline = entry.title
        relevant = already_classified or ai_service.classify(headline)
        link = entry.link

        if not is_safe_article_url(link):
            return None
        if not relevant:
            return None
        article_content = get_article_content(link)
        if article_content == "empty article.":
            return None

        translated_headline = ai_service.translate_headline(headline)
        processed_article = ai_service.summarize(
            headline,
            article_content,
        )

        if not processed_article:
            return None

        summary = processed_article.summary
        references_original = processed_article.references
        references = processed_article.references_for_translation
        tags = processed_article.tags

        try:
            references_translated = translate_references(references)
        except Exception as exception:
            add_log(
                f"{headline}: reference translation failed "
                f"({type(exception).__name__}): {exception}; saving article "
                f"with untranslated references"
            )
            references_translated = references_original.copy()

        article_overview = (
            f"{translated_headline}:{summary}"
        )

        try:
            vector = vector_service.embed(article_overview)
        except Exception as exception:
            add_log(
                f"exception: {type(exception).__name__}: "
                f"{exception}; failed to embed article overview: "
                f"{article_overview}"
            )
            vector = None

        published_at = item_published_at(entry)

        return (
            headline,
            translated_headline,
            link,
            summary,
            references_original,
            references_translated,
            tags,
            vector,
            published_at,
            processed_article.neutral_fact.model_dump(),
        )
    except Exception as exception:
        add_log(
            f"{headline}: failed to process article "
            f"({type(exception).__name__}): {exception}"
        )
        return None


def setup_event_clusterer(
    ai_service: AIService,
    run_id: int,
) -> EventClusterer | None:
    if not EVENT_CLUSTERING_ENABLED:
        return None
    try:
        vectors = EventVectorStore(EVENTS_COLLECTION)
        vectors.ensure()
        session = SessionLocal()
        return EventClusterer(session, vectors, ai_service, run_id)
    except Exception as exception:
        add_log(
            f"event clustering failed to initialize "
            f"({type(exception).__name__}): {exception}"
        )
        return None


def cluster_new_article(
    clusterer: EventClusterer,
    article: Articles,
    country: str,
) -> bool:
    try:
        fact = (article.neutral_fact or {}).get("fact")
        vectors = clusterer.vectors.article_vectors([article.id])
        vector = vectors.get(article.id)
        if not fact or not vector:
            add_log(
                f"event clustering skipped article {article.id}: "
                f"missing fact vector"
            )
            return False
        clusterer.process(ReplayArticle(
            id=article.id,
            source_id=article.source_id,
            country=country,
            fact=article.neutral_fact,
            vector=vector,
            observed_at=article.published_at or article.captured_at,
        ))
        clusterer.session.commit()
        return True
    except Exception as exception:
        clusterer.session.rollback()
        add_log(
            f"event clustering failed for article {article.id} "
            f"({type(exception).__name__}): {exception}"
        )
        return False


def pending_cluster_articles(run_id: int):
    observed = func.coalesce(Articles.published_at, Articles.captured_at)
    ordering = (observed, Articles.id, PendingItem.outlet_id, PendingItem.guid)
    cursor = None
    while True:
        with SessionLocal() as session:
            query = (
                session.query(PendingItem, Articles, Countries.name)
                .join(Articles, Articles.id == PendingItem.article_id)
                .join(Sources, Sources.id == PendingItem.outlet_id)
                .join(Countries, Countries.id == Sources.country_id)
                .join(ArticleAppearances, (ArticleAppearances.run_id == PendingItem.run_id) &
                      (ArticleAppearances.source_id == PendingItem.outlet_id) &
                      (ArticleAppearances.article_id == PendingItem.article_id))
                .filter(PendingItem.run_id == run_id)
            )
            if cursor is not None:
                query = query.filter(tuple_(*ordering) > tuple_(*cursor))
            batch = query.order_by(*ordering).limit(25).all()
        if not batch:
            return
        pending, article, _ = batch[-1]
        cursor = (article.published_at or article.captured_at, article.id,
                  pending.outlet_id, pending.guid)
        yield from batch


def main() -> None:
    if MAX_ITEMS_PER_OUTLET_PER_RUN < 1:
        raise ValueError("MAX_ITEMS_PER_OUTLET_PER_RUN must be positive")

    ai_service, vector_service, run_time, data = setup()
    run_id = start_ingestion_run(run_time)
    configured_sources = sum(len(sources) for sources in data.values())
    successful_sources = 0
    event_clusterer = setup_event_clusterer(ai_service, run_id)
    completed = False

    try:
        for country, sources in data.items():
            country_object = get_country(country)
            if not country_object:
                continue
            for source, config in sources.items():
                source_result = get_source(country_object, country, source, config)
                if not source_result:
                    continue
                source_object, source_name, url = source_result
                log = OutletRunLog(
                    run_id=run_id, outlet_id=source_object.id, feed_size=0,
                    new_items=0, political=0, processed=0, skipped_by_cap=0,
                    gap=False, cheap_pass_calls=0, full_pass_calls=0,
                    input_tokens=0, output_tokens=0,
                )
                input_start = ai_service.input_tokens + vector_service.input_tokens
                output_start = ai_service.output_tokens
                try:
                    feed = validate_feed(url, country, source_name)
                    entries = feed.entries if feed is not None else []
                    if entries:
                        successful_sources += 1
                    log.feed_size = len(entries)
                    items = []
                    for entry in entries:
                        try:
                            link = getattr(entry, "link", "")
                            guid = normalize_item_guid(getattr(entry, "id", ""), link)
                            normalized = normalize_article_url(link)
                            items.append((entry, guid, normalized, item_published_at(entry)))
                        except (ValueError, TypeError, AttributeError) as exception:
                            add_log(f"{country} / {source_name}: invalid feed item ({exception})")
                    seen, has_history = get_seen_items(
                        source_object.id,
                        list({key for _, guid, link, _ in items for key in (guid, link)}),
                    )
                    log.gap = feed is not None and has_history and not any(
                        guid in seen or link in seen for _, guid, link, _ in items
                    )
                    if log.gap:
                        add_log(f"WARNING: {country} / {source_name}: no known feed items; possible ingestion gap")
                    for entry, guid, normalized, published_at in items:
                        if guid not in seen and normalized not in seen:
                            try:
                                queue_item(source_object.id, guid, run_id, run_time,
                                           getattr(entry, 'link', ''),
                                           getattr(entry, 'title', '') or '', published_at)
                            except Exception as exception:
                                add_log(f"{country} / {source_name}: could not queue item "
                                        f"({type(exception).__name__}): {exception}")
                    feed_guids = {guid for _, guid, _, _ in items}
                    feed_pending = get_feed_pending(source_object.id, feed_guids)
                    def queued_items():
                        for pending in get_pending_items(source_object.id, feed_guids):
                            entry = SimpleNamespace(
                                link=pending.link, title=pending.headline,
                                published_parsed=(pending.published_at.utctimetuple()
                                                  if pending.published_at else None),
                            )
                            yield (entry, pending.guid, normalize_article_url(pending.link),
                                   pending.published_at, pending)
                    minimum = datetime.min.replace(tzinfo=timezone.utc)
                    items.sort(key=lambda item: item[3] or minimum, reverse=True)
                    feed_items = ((entry, guid, normalized, published_at, feed_pending.get(guid))
                                  for entry, guid, normalized, published_at in items)
                    ordered_items = heapq.merge(feed_items, queued_items(),
                                                key=lambda item: item[3] or minimum,
                                                reverse=True)
                    position = 0
                    accepted = 0
                    keys = set()
                    for entry, guid, normalized, published_at, pending in ordered_items:
                        if guid in feed_guids:
                            if guid in keys:
                                continue
                            keys.add(guid)
                        try:
                            link = getattr(entry, "link", "")
                            article = None
                            if pending is not None and pending.article_id is not None:
                                with SessionLocal() as session:
                                    article = session.get(Articles, pending.article_id)
                            known = pending is None and (guid in seen or normalized in seen)
                            if article is None:
                                article = find_article_by_url(normalized, link)
                            if not known and guid in feed_guids:
                                log.new_items += 1
                            if known:
                                if guid not in seen:
                                    mark_item_seen(source_object.id, guid, run_time)
                                    seen.add(guid)
                                if article and stage_appearance(run_id, source_object.id, article.id, position):
                                    position += 1
                                continue

                            retrying = pending is not None and pending.political
                            if not retrying and article is not None:
                                with SessionLocal() as session:
                                    retrying = (
                                        session.query(PendingItem.article_id)
                                        .filter_by(article_id=article.id).first() is not None
                                    )

                            if article and not retrying and (pending is None or pending.article_id is None):
                                if pending is None:
                                    mark_item_seen(source_object.id, guid, run_time)
                                else:
                                    complete_pending_item(source_object.id, guid)
                                seen.add(guid)
                                if stage_appearance(run_id, source_object.id, article.id, position):
                                    position += 1
                                continue

                            if pending is None:
                                queue_item(source_object.id, guid, run_id, run_time, link,
                                           getattr(entry, 'title', '') or '', published_at)
                            if not retrying:
                                log.cheap_pass_calls += 1
                                if not ai_service.classify(getattr(entry, "title", "")):
                                    complete_pending_item(source_object.id, guid)
                                    seen.add(guid)
                                    continue
                                mark_pending_political(source_object.id, guid)
                            elif pending is None:
                                mark_pending_political(source_object.id, guid)
                            log.political += 1
                            if accepted >= MAX_ITEMS_PER_OUTLET_PER_RUN:
                                log.skipped_by_cap += 1
                                continue
                            accepted += 1
                            if article is None:
                                log.full_pass_calls += 1
                                info = get_article_info(entry, ai_service, vector_service, already_classified=True)
                                if not info:
                                    continue
                                (headline, translated_headline, link, summary, references,
                                 translated, tags, vector, published_at, neutral_fact) = info
                                article = Articles(
                                    source_id=source_object.id, headline=headline,
                                    translated_headline=translated_headline, link=link,
                                    summary=summary, references_original=references,
                                    references_translated=translated, tags=tags,
                                    embedding=vector, published_at=published_at,
                                    neutral_fact=neutral_fact, captured_at=run_time,
                                )
                                article = add_canonical_article(
                                    article, normalized,
                                    pending={"outlet_id": source_object.id, "guid": guid,
                                             "run_id": run_id, "first_seen": run_time},
                                )
                            stage_pending_item(source_object.id, guid, article.id, run_id, run_time)
                            upsert_article(article, vector_service)
                            if stage_appearance(run_id, source_object.id, article.id, position):
                                position += 1
                                if not entries:
                                    successful_sources += 1
                            if not EVENT_CLUSTERING_ENABLED:
                                complete_pending_item(source_object.id, guid)
                            log.processed += 1
                        except Exception as exception:
                            add_log(f"{country} / {source_name}: item failed ({type(exception).__name__}): {exception}")
                    if log.skipped_by_cap:
                        add_log(f"{country} / {source_name}: cap hit; {log.skipped_by_cap} political items deferred")
                except Exception as exception:
                    add_log(f"{country} / {source_name}: feed failed ({type(exception).__name__}): {exception}")
                finally:
                    log.input_tokens = ai_service.input_tokens + vector_service.input_tokens - input_start
                    log.output_tokens = ai_service.output_tokens - output_start
                    try:
                        if save_outlet_run_log(log):
                            add_log(f"WARNING: {country} / {source_name}: cap hit for three consecutive runs")
                    except Exception as exception:
                        add_log(f"{country} / {source_name}: run log failed ({type(exception).__name__}): {exception}")

        if configured_sources == 0 or successful_sources == 0:
            raise RuntimeError("Ingestion run has no successfully fetched feeds")
        complete_ingestion_run(run_id, [])
        completed = True
    except Exception:
        fail_ingestion_run(run_id)
        raise
    finally:
        if event_clusterer:
            try:
                if completed:
                    for pending, article, country in pending_cluster_articles(run_id):
                        with SessionLocal() as session:
                            already_clustered = session.get(ArticleEvents, article.id) is not None
                        input_start = ai_service.input_tokens
                        output_start = ai_service.output_tokens
                        clustered = already_clustered or cluster_new_article(event_clusterer, article, country)
                        add_outlet_token_usage(run_id, pending.outlet_id,
                                               ai_service.input_tokens - input_start,
                                               ai_service.output_tokens - output_start)
                        if clustered:
                            complete_pending_item(pending.outlet_id, pending.guid)
                input_start = ai_service.input_tokens
                output_start = ai_service.output_tokens
                event_clusterer.finalize()
                event_clusterer.session.commit()
                add_log(f"event finalization tokens: input={ai_service.input_tokens - input_start}, "
                        f"output={ai_service.output_tokens - output_start}")
            except Exception as exception:
                event_clusterer.session.rollback()
                add_log(f"event clustering failed to finalize ({type(exception).__name__}): {exception}")
        if event_clusterer:
            event_clusterer.session.close()


if __name__ == "__main__":
    main()
