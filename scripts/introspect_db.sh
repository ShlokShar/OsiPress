#!/usr/bin/env bash
#
# READ-ONLY database introspection. Runs no DDL and writes nothing to the
# database. Used to capture the production schema so the Alembic baseline
# revision (0001) can be written to match reality rather than to match
# shared/models.py, which has drifted from it.
#
# Usage:
#   ./scripts/introspect_db.sh "postgresql://user:pw@host:5432/osipress" OUTDIR
#
# The URL is taken as an argument and never stored in the output.

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: $0 <database-url> [outdir]" >&2
    exit 64
fi

URL="$1"
OUT="${2:-./introspect-out}"
mkdir -p "$OUT"

echo "writing to $OUT"

# The authoritative artifact: exact DDL for everything in the public schema.
pg_dump --schema-only --no-owner --no-privileges --no-comments \
        --no-security-labels --no-tablespaces -d "$URL" > "$OUT/schema.sql"

psql "$URL" -Atc \
  "select extname, extversion from pg_extension order by 1" \
  > "$OUT/extensions.txt"

psql "$URL" -Atc "
select table_name, ordinal_position, column_name, data_type,
       character_maximum_length, is_nullable, column_default
from information_schema.columns
where table_schema = 'public'
order by table_name, ordinal_position" \
  > "$OUT/columns.txt"

psql "$URL" -Atc \
  "select indexdef from pg_indexes where schemaname='public' order by indexname" \
  > "$OUT/indexes.txt"

psql "$URL" -Atc "
select conrelid::regclass::text, conname, pg_get_constraintdef(oid)
from pg_constraint
where connamespace = 'public'::regnamespace
order by 1, 2" \
  > "$OUT/constraints.txt"

psql "$URL" -Atc "select to_regclass('public.alembic_version') is not null" \
  > "$OUT/has_alembic.txt"

psql "$URL" -Atc "
select table_name from information_schema.tables
where table_schema='public' order by table_name" \
  > "$OUT/tables.txt"

# The data facts revision 0003 depends on: which columns can actually take a
# NOT NULL, and whether articles.link has duplicates (it must NOT get a
# unique index if so).
psql "$URL" -Atc "
select
  count(*)                                              as total,
  count(*) filter (where source_id is null)             as null_source_id,
  count(*) filter (where headline is null)              as null_headline,
  count(*) filter (where translated_headline is null)   as null_translated,
  count(*) filter (where link is null)                  as null_link,
  count(*) filter (where summary is null)               as null_summary,
  count(*) filter (where references_original is null)   as null_refs_orig,
  count(*) filter (where references_translated is null) as null_refs_trans,
  count(*) filter (where tags is null)                  as null_tags,
  count(*) filter (where embedding is null)             as null_embedding,
  count(distinct link)                                  as distinct_links
from articles" \
  > "$OUT/articles_facts.txt"

psql "$URL" -Atc "
select 'countries' as t, count(*) as rows,
       count(*) filter (where name is null) as null_name,
       0 as null_other
from countries
union all
select 'sources', count(*),
       count(*) filter (where name is null),
       count(*) filter (where country_id is null)
     + count(*) filter (where political_leaning is null)
     + count(*) filter (where link is null)
from sources" \
  > "$OUT/refs_facts.txt"

echo
echo "--- tables ---";      cat "$OUT/tables.txt"
echo "--- extensions ---";  cat "$OUT/extensions.txt"
echo "--- alembic_version exists? ---"; cat "$OUT/has_alembic.txt"
echo "--- indexes ---";     cat "$OUT/indexes.txt"
echo "--- articles facts (total|nulls...|distinct_links) ---"
cat "$OUT/articles_facts.txt"
echo "--- countries/sources facts ---"
cat "$OUT/refs_facts.txt"
echo
echo "done. full DDL in $OUT/schema.sql"
