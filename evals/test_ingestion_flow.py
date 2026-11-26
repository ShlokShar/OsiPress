from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import cron.script as ingestion
from cron.ai.service import AIService


class Session:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, *args):
        return None


def run_feed(monkeypatch, entries, info, pending=None):
    seen = []
    logs = []
    queued = {item.guid: (item, article) for item, article in (pending or [])}
    ai = SimpleNamespace(input_tokens=0, output_tokens=0,
                         classify=lambda title: title != 'sport')
    vectors = SimpleNamespace(input_tokens=0)
    monkeypatch.setattr(ingestion, 'setup', lambda: (ai, vectors, datetime.now(timezone.utc),
                                                     {'Iran': {'one': {}}}))
    monkeypatch.setattr(ingestion, 'get_country', lambda country: SimpleNamespace(id=1))
    monkeypatch.setattr(ingestion, 'get_source', lambda *args: (SimpleNamespace(id=1), 'outlet', 'feed'))
    monkeypatch.setattr(ingestion, 'validate_feed', lambda *args: SimpleNamespace(entries=entries))
    monkeypatch.setattr(ingestion, 'get_seen_items', lambda *args: (set(), False))
    monkeypatch.setattr(ingestion, 'get_feed_pending', lambda outlet, guids: {
        guid: queued[guid][0] for guid in guids if guid in queued
    })
    monkeypatch.setattr(ingestion, 'get_pending_items', lambda outlet, guids: (
        item for guid, (item, _) in queued.items() if guid not in guids
    ))
    def queue(outlet, guid, run_id, first_seen, link, headline, published_at):
        queued.setdefault(guid, (SimpleNamespace(guid=guid, link=link, headline=headline,
                                                 published_at=published_at, political=False,
                                                 article_id=None), None))
    monkeypatch.setattr(ingestion, 'queue_item', queue)
    monkeypatch.setattr(ingestion, 'mark_pending_political', lambda outlet, guid: setattr(queued[guid][0], 'political', True))
    monkeypatch.setattr(ingestion, 'find_article_by_url', lambda *args: None)
    class FeedSession(Session):
        def get(self, model, key):
            if model is ingestion.Articles:
                return next((article for _, article in queued.values()
                             if article is not None and article.id == key), None)
            return None
    monkeypatch.setattr(ingestion, 'SessionLocal', FeedSession)
    monkeypatch.setattr(ingestion, 'start_ingestion_run', lambda *args: 1)
    monkeypatch.setattr(ingestion, 'complete_ingestion_run', lambda *args: True)
    monkeypatch.setattr(ingestion, 'setup_event_clusterer', lambda *args: None)
    monkeypatch.setattr(ingestion, 'get_article_info', info)
    monkeypatch.setattr(ingestion, 'MAX_ITEMS_PER_OUTLET_PER_RUN', 1)
    monkeypatch.setattr(ingestion, 'EVENT_CLUSTERING_ENABLED', False)
    monkeypatch.setattr(ingestion, 'mark_item_seen', lambda outlet, guid, now: seen.append(guid))
    monkeypatch.setattr(ingestion, 'complete_pending_item', lambda outlet, guid: seen.append(guid))
    monkeypatch.setattr(ingestion, 'save_outlet_run_log', lambda log: logs.append(log) or False)
    monkeypatch.setattr(ingestion, 'stage_pending_item', lambda *args: None)
    monkeypatch.setattr(ingestion, 'stage_appearance', lambda *args: True)
    monkeypatch.setattr(ingestion, 'upsert_article', lambda *args: None)
    monkeypatch.setattr(ingestion, 'add_canonical_article', lambda article, *args, **kwargs: article)
    monkeypatch.setattr(ingestion, 'add_log', lambda *args: None)
    ingestion.main()
    return seen, logs[0]


def entry(name, day):
    return SimpleNamespace(id=name, title=name, link=f'https://example.com/{name}',
                           published_parsed=(2026, 11, day, 0, 0, 0))


def test_failed_and_deferred_items_remain_unseen(monkeypatch):
    seen, log = run_feed(monkeypatch, [entry('old', 1), entry('sport', 2), entry('failed', 3)],
                         lambda *args, **kwargs: None)
    assert seen == ['sport']
    assert (log.new_items, log.political, log.processed, log.skipped_by_cap) == (3, 2, 0, 1)


def test_successful_item_is_marked_seen(monkeypatch):
    def info(entry, *args, **kwargs):
        return (entry.title, entry.title, entry.link, 'summary', [], [], [], None, None, {'fact': 'fact'})
    seen, log = run_feed(monkeypatch, [entry('success', 1)], info)
    assert seen == ['success']
    assert log.processed == 1


def test_empty_headline_is_a_retryable_failure():
    with pytest.raises(ValueError, match='empty headline'):
        AIService.classify(None, '')


def test_pending_article_missing_from_feed_is_retried_without_reclassification(monkeypatch):
    article = SimpleNamespace(id=42, link='https://example.com/missing', headline='sport',
                              published_at=None, captured_at=datetime.now(timezone.utc))
    item = SimpleNamespace(guid='opaque-guid', link=article.link, headline=article.headline,
                           published_at=None, political=True, article_id=article.id)
    seen, log = run_feed(monkeypatch, [], lambda *args, **kwargs: None,
                         pending=[(item, article)])
    assert seen == ['opaque-guid']
    assert (log.processed, log.cheap_pass_calls, log.new_items) == (1, 0, 0)


def test_finalization_runs_when_all_feeds_are_empty(monkeypatch):
    finalized = []
    ai = SimpleNamespace(input_tokens=0, output_tokens=0)
    vectors = SimpleNamespace(input_tokens=0)
    session = SimpleNamespace(commit=lambda: None, close=lambda: None, rollback=lambda: None)
    clusterer = SimpleNamespace(session=session, finalize=lambda: finalized.append(True))
    monkeypatch.setattr(ingestion, 'setup', lambda: (ai, vectors, datetime.now(timezone.utc),
                                                     {'Iran': {'one': {}}}))
    monkeypatch.setattr(ingestion, 'start_ingestion_run', lambda *args: 1)
    monkeypatch.setattr(ingestion, 'setup_event_clusterer', lambda *args: clusterer)
    monkeypatch.setattr(ingestion, 'get_country', lambda *args: object())
    monkeypatch.setattr(ingestion, 'get_source', lambda *args: (SimpleNamespace(id=1), 'outlet', 'url'))
    monkeypatch.setattr(ingestion, 'validate_feed', lambda *args: SimpleNamespace(entries=[]))
    monkeypatch.setattr(ingestion, 'get_seen_items', lambda *args: (set(), False))
    monkeypatch.setattr(ingestion, 'get_feed_pending', lambda *args: {})
    monkeypatch.setattr(ingestion, 'get_pending_items', lambda *args: iter(()))
    monkeypatch.setattr(ingestion, 'save_outlet_run_log', lambda *args: False)
    monkeypatch.setattr(ingestion, 'fail_ingestion_run', lambda *args: None)
    monkeypatch.setattr(ingestion, 'add_log', lambda *args: None)
    with pytest.raises(RuntimeError, match='no successfully fetched feeds'):
        ingestion.main()
    assert finalized == [True]
