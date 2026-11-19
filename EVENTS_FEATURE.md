# OsiPress: Event Clustering — Repository-Specific Handoff

## Current architecture and schema

Ingestion starts in `cron/script.py::main`: RSS entries are processed by
`get_article_info()`, `cron.ai.service.AIService`, `shared.models.add_canonical_article`,
and `cron.util.backfill_vectors.upsert_article`. A successful edition is published
through `shared.models.complete_ingestion_run()` and `article_appearances`.

`main.py::today` and `main.py::archive` call
`shared.models.get_headlines_by_country()`, which returns the existing
country → outlet → article board rendered by `templates/index.html` and
`static/js/osipress.js`.

Production schema (Alembic `0003_search_indexes`) already has:

| Table | Existing fields to reuse |
|---|---|
| `countries` | `id`, `name` |
| `sources` | `id`, `country_id`, `name`, `link`, `political_leaning` |
| `articles` | `id`, `source_id`, `headline`, `translated_headline`, `link`, `summary`, references arrays, `captured_at`, `tags`, `embedding` |
| `ingestion_runs` | `id`, `started_at`, `completed_at`, `status` |
| `article_appearances` | `run_id`, `source_id`, `article_id`, `position` |
| `article_urls` | canonical normalized URL → `article_id` |

`articles.id` is also the Qdrant `articles` point id and must never be
renumbered. The remote `articles` collection currently stores named `dense`
(1536-dimensional) and `sparse` vectors. Postgres is the source of truth.

## Goal

Group articles into **events** so the homepage shows stories, not outlets.
Each event card shows Iranian and Israeli coverage of the same development side
by side, using real articles. The only AI-written text on a card is a neutral
title.

## Concepts

- **Topic**: long-lived, hand-curated subject, with a name and one-line description.
- **Event**: one specific development, created automatically and lasting days.
- **Article**: belongs to at most one event; belongs to a topic through its event.

## Non-goals for v1

- No AI summaries, coverage-so-far, or what-changed text.
- No topic timeline pages, following, digests, entities, or analytics pages.
- No outlet expansion; retain the per-outlet cap as configuration (`MAX_ARTICLES`
  in `cron/script.py` is currently `3`).

## Work in phases

Do one phase per task. Read the listed dependencies and propose a short plan
before writing code. Stop at the end of each phase and report.

---

## Phase 1 — Data foundation

### 1. RSS `published_at`

Add nullable `articles.published_at TIMESTAMP WITH TIME ZONE`. It stores an
entry's RSS `pubDate` in UTC and is null when unavailable. Keep
`articles.captured_at` unchanged as the ingestion timestamp and ordering
fallback.

- Change `cron/script.py::get_article_info()` and its `ArticleInfo` tuple to
  carry parsed feed publication time to the `Articles(...)` construction in
  `cron/script.py::main`.
- Add the column to `shared.models.Articles` and in a new migration after
  `migrations/versions/0003_search_fallback_indexes.py`.
- Backfill only from trustworthy stored source data; otherwise leave null.

### 2. Neutral fact extraction

Extend the existing `AIService.summarize()` call; do not create another model
call. Add `NeutralFact` to `cron/ai/schemas.py` and include it in `Parsed`:

```text
actors: list[str]
action: str
target: str | None
location: str | None
date: str | None
fact: str
```

Extend `cron/ai/prompts.py::SUMMARIZE_INSTRUCTIONS`, consumed by
`cron/ai/service.py::AIService.summarize`, while preserving its existing date
post-processing. Store the validated object in nullable `articles.neutral_fact
JSONB`; `neutral_fact.fact` is the canonical fact line.

Fact rules remain: one English sentence; canonical English names and consistent
transliteration; normalize loaded terms (for example, “Zionist regime” →
“Israel”); no adjectives, motive, casualty framing, or blame attribution.

### 3. Embed the fact line

Add a named 1536-dimensional `fact` vector to the existing Qdrant `articles`
collection. Keep `dense`, `sparse`, and `Articles.embedding` unchanged.

- Update `cron/util/backfill_vectors.py::create_collection`, `build_points`,
  and `upsert_article` to configure and send the fact vector.
- Update the existing remote collection in place; never recreate it or change
  its existing points' ids.
- Keep the source fact in `articles.neutral_fact`; do not add another Postgres
  vector column.

### 4. Backfill

Add a dedicated `cron/events/fact_backfill.py`. It must stream in stable,
bounded id batches; be resumable and idempotent; skip rows with both a stored
fact and Qdrant fact vector; and use the extended existing summarization call.

Do not copy the full-archive `.all()` behavior currently used by
`cron/util/backfill.py::backfill` and
`cron/util/backfill_vectors.py::backfill_vectors`.

### 5. Event schema

Add models to `shared/models.py` and the next Alembic revision:

```text
topics(id, name, description)
events(id, topic_id NULL -> topics.id, title NULL,
       status hidden|visible, outlet_count, article_count,
       first_seen, last_seen, first_published_at, titled_at NULL)
article_events(article_id PK -> articles.id, event_id -> events.id,
               joined_at, match_path high|low|judge, match_score NULL)
match_log(id, run_id NULL -> ingestion_runs.id, article_id -> articles.id,
          candidates JSONB, decision, path high|low|judge, created_at)
```

Use database check constraints for `events.status`, `article_events.match_path`,
and `match_log.path`. `article_events.article_id` as the primary key enforces
one event per article.

Do **not** add `events.countries text[]`: derive country coverage from the
existing chain `article_events → articles → sources → countries`. The required
stored `article_count` and `outlet_count` remain event counters for promotion
and ranking.

### Phase 1 files

| File | Change or dependency |
|---|---|
| `shared/models.py` | Add `published_at`, `neutral_fact`, and `Topics`, `Events`, `ArticleEvents`, `MatchLog`; reuse existing foreign-key models. |
| `migrations/versions/0004_*.py` | Add two `articles` columns, event tables, foreign keys, constraints, and indexes. |
| `cron/ai/schemas.py` | Add `NeutralFact` to `Parsed`. |
| `cron/ai/prompts.py` | Add structured neutral-fact rules to `SUMMARIZE_INSTRUCTIONS`. |
| `cron/ai/service.py` | Preserve `AIService.summarize()` and existing date handling. |
| `cron/script.py` | Parse RSS publication time; persist fact data; pass facts into Qdrant indexing. |
| `cron/util/backfill_vectors.py` | Add `fact` vector configuration and point data. |
| `cron/events/fact_backfill.py` (new) | Streaming, resumable fact/vector backfill. |
| `scripts/audit_qdrant.py` | Extend only if fact-vector coverage needs read-only auditing. |

---

## Phase 2 — Clustering engine (offline / dry-run first)

Create modules under `cron/events/`, callable by cron and a replay CLI. Replay
the archive in `COALESCE(articles.published_at, articles.captured_at)` order,
streaming rows. The CLI uses an isolated Postgres target and Qdrant
`events_eval`, never production event rows or the production `events`
collection.

Create remote Qdrant collection `events`, with named 1536-dimensional vectors:
`centroid` (mean of ten most-recent member fact vectors) and `anchor` (the
first article's fact vector). Point ids equal `events.id`; payload has `status`
and `last_seen`.

For every article, sequentially:

1. Query `events` whose `last_seen` is within `WINDOW_DAYS`, any status, for
   `TOP_K` centroid candidates.
2. Rescore: `ANCHOR_WEIGHT * cos(anchor) + (1 - ANCHOR_WEIGHT) * cos(centroid)`.
3. Best score ≥ `HIGH`: join (`high`). Best score < `LOW`: hidden event
   (`low`). Otherwise judge (`judge`) with the article fact, each top-three
   candidate title when present, and three recent candidate fact lines; strict
   JSON is `{"event_id": <id> | null}`. Null creates an event.
4. On join, recompute centroid from ten most-recent fact vectors; update counts,
   `last_seen`, and `first_published_at`. Derive country coverage using the
   existing joins. Make changes visible to later articles in the same run.
5. Write a `match_log` row for every decision using the current run id.

At end of run:

1. Promote hidden → visible at `article_count ≥ PROMOTE_MIN_ARTICLES` and
   `outlet_count ≥ PROMOTE_MIN_OUTLETS`.
2. For visible, both-country, untitled events, make one title call with both
   countries' fact lines and `topics`; strict JSON is
   `{"title": str, "topic_id": int | null}`. Titles are short, neutral, and
   only state what both countries' reporting agrees happened. Set once, never
   regenerate in v1; failures remain null for retry next run.
3. Delete hidden events older than `WINDOW_DAYS`, their `article_events`, and
   their Qdrant points. Never delete visible events.

`cron/events/config.py` is the single tunable location:

```text
HIGH = 0.80
LOW = 0.60
TOP_K = 10
WINDOW_DAYS = 7
ANCHOR_WEIGHT = 0.5
PROMOTE_MIN_ARTICLES = 3
PROMOTE_MIN_OUTLETS = 2
CENTROID_RECENT_N = 10
```

The dry-run report must be printed and written after a full replay: created /
promoted / visible-both-country counts; per-day visible cross-country mean,
median, min, max; same-country versus cross-country score histogram; judge
calls/outcomes; and ten largest events with fact lines. Export approximately
150 stratified `match_log` rows: 50 judge-band, 50 cross-country joins, 25
high, 25 low, with article fact, outlet/country, three candidate fact lines,
score, decision, and empty `correct`.

### Phase 2 files

| File | Change or dependency |
|---|---|
| `cron/events/config.py` (new) | All listed thresholds and limits. |
| `cron/events/cluster.py` (new) | Sequential decisions and relational writes. |
| `cron/events/vector_store.py` (new) | Qdrant `events`/`events_eval` creation, candidate query, upsert, delete. Follow `cron/util/backfill_vectors.py` client patterns. |
| `cron/events/replay.py` (new) | Streaming replay, isolated target, report, labeling export. |
| `shared/models.py` | Event-membership, recent-fact, count, and country-coverage query helpers. |
| `shared/database.py` | Current `SessionLocal` targets the normal public schema; it cannot be used unchanged for dry run. |
| `cron/ai/service.py`, `cron/ai/schemas.py` | Strict Pydantic judge/title output added only in this phase. |

**Stop after Phase 2.** Set thresholds from hand-labeled data before production.

---

## Phase 3 — Production wiring

Wire clustering into `cron/script.py::main` after a new canonical article has
its fact persisted and its Qdrant `fact` vector available. Put it behind a
configuration flag. Preserve this existing path:

```text
find_article_by_url -> get_article_info -> add_canonical_article
-> upsert_article -> complete_ingestion_run
```

Cluster only newly processed canonical rows, not duplicates returned by
`find_article_by_url`. Pass the `run_id` from `start_ingestion_run` to
`match_log`. Clustering failures use `cron.util.log.add_log` and continue;
they must not call `fail_ingestion_run` or prevent `complete_ingestion_run`.

| File | Change or dependency |
|---|---|
| `cron/script.py` | Flagged clustering call with non-fatal failure isolation. |
| `cron/events/cluster.py` | Production entry point from Phase 2. |
| `cron/util/log.py` | Existing durable error log. |
| `cron/ai/service.py` | Existing LLM boundary; event judge/title client must remain swappable and provider-configurable. |
| `shared/models.py` | Existing run lifecycle plus event persistence. |

---

## Phase 4 — Frontend

`main.py::landing` currently owns `/`, sets the `visited` cookie, and redirects
returning users to `/today`. `main.py::today` renders `templates/index.html`.
Add an event-read query in `shared/models.py` using:

```text
events -> article_events -> articles -> sources -> countries
```

Use `article_appearances.run_id` and `ingestion_runs` for latest-run badges.
Use the same joins for country/outlet grouping, leanings, and coverage dots.
Do not put `Articles.summary` into event card data or rendering: v1 cards show
real article headlines and links only.

Homepage behavior remains:

- Top stories: visible, both-country events, ranked by article plus outlet
  activity in the last 24 hours, then `last_seen`.
- Current homepage content becomes All today.
- One card: topic pill; neutral title; `since {first_published_at} ·
  {article_count} articles · {outlet_count} outlets`; coverage dots for every
  existing `sources` row, with `not found in feed` for hollow dots; Iran then
  Israel; outlet groups ordered across each spectrum; original linked headline,
  translated headline, leaning, and `published_at`; newest three per country
  plus `+N more`; latest-run and localStorage last-visit NEW badges; larger
  lead-event title.
- Do not show single-country events.
- Preserve the cream/orange/serif/bracket visual system in
  `static/css/osipress.css` and current templates.

| File | Change or dependency |
|---|---|
| `main.py` | `landing`, `today`, routes, and template context. |
| `shared/models.py` | Event query; keep `get_headlines_by_country` for All today/archive. |
| `templates/index.html` | Existing country/outlet board; retain for All today or split event view. |
| `templates/landing.html` | Existing first-visit page, dependent on route decision. |
| `static/js/osipress.js` | Current `buildStory()` renders summaries; event renderer must not reuse that behavior. |
| `static/css/osipress.css` | Existing brand and responsive layout tokens. |
| `templates/events.html`, `static/js/events.js` (new, if split) | Event-specific payload and interactions. |
| `templates/archive.html`, `static/js/archive.js` | Keep archive on `get_headlines_by_country`; no event archive in v1. |

---

## Constraints

- No code comments.
- Pydantic for every LLM structured response; reject and retry once on invalid JSON.
- Idempotent, resumable, streaming backfills.
- No full run/archive loads into memory and no new long-running VPS processes.
- Do not alter `articles.id`; preserve existing `dense` and `sparse` vectors.

## Open questions

1. **Route conflict:** `/` is the current cookie-gated landing route but must
   become Top stories. **Recommended:** move the current first-visit experience
   to `/welcome`, use `/` for Top stories, retain `/today` for All today.
2. **Historical publication times:** no stored RSS payload or `pubDate` exists
   for current rows. **Recommended:** leave them null and replay using
   `COALESCE(published_at, captured_at)` rather than infer dates.
3. **Topic ownership:** no admin UI, CLI, seed, or migration data currently
   manages hand-curated topics. **Recommended:** choose an initial reviewed
   seed migration or operator-only CLI before Phase 2.
4. **Swappable LLM conflict:** `AIService` directly instantiates `OpenAI` with
   fixed defaults today. **Recommended:** choose whether event judge/title work
   extends `AIService` or gets a provider interface before Phase 2; do not add
   a second hard-coded OpenAI path.
5. **Dry-run isolation:** `shared.database.SessionLocal` targets normal public
   tables. **Recommended:** select a dedicated Postgres schema explicitly in
   the replay CLI and pair it with `events_eval`, keeping existing article
   tables read-only during replay.
