
from typing import (
    get_args,
)

from cron.ai.tags import ALLOWED_TAGS

CLASSIFY_INSTRUCTIONS = """You classify RSS news headlines.

Classify whether a headline is political if it is about:
- Politics
- Government policy
- Elections
- Diplomacy
- International relations
- Military affairs or conflict
- National security
- Sanctions
- Macroeconomics or economic policy

Do not classify a headline as political if it is primarily about:
- Sports
- Entertainment
- Celebrities
- Lifestyle
- Technology
- Science
- Health
- Weather"""


SOLAR_DATE_OUTPUT_RULES = """Add only complete Iranian Solar Hijri dates to a
dates field. A complete date must explicitly contain its year, month, and day in
the same individual date expression. Never infer a missing component from another
date, nearby text, the publication date, or the current date.

Before adding any date item, verify that its exact source expression explicitly
supplies all three components. If even one component is absent, do not add an item.
Never invent a conventional day such as 1 or 30, and never borrow a year such as
1405 from the surrounding sentence. A date inside a range is ineligible even when
each endpoint appears complete.

Replace each complete date with one matching DATE_<index> placeholder. Every date
item must have exactly one placeholder in the same text field, and every placeholder
must have exactly one date item.

Do not add incomplete, ranged, or ambiguous dates to a dates field. Translate them
naturally without placeholders or Gregorian conversion. Transliterate Solar Hijri
month names and preserve every explicitly supplied component: ۳ تیر becomes Tir 3,
تیر ۱۴۰۵ becomes Tir 1405, and تیر becomes Tir. Preserve ambiguous numeric forms
such as 03/04/1405 rather than choosing an interpretation. Translate date ranges
naturally without extracting either endpoint for conversion. Use Latin digits in
English output, but do not otherwise change an incomplete date's precision.

Recognize the fixed Solar Hijri month mapping: Farvardin=1, Ordibehesht=2,
Khordad=3, Tir=4, Mordad=5, Shahrivar=6, Mehr=7, Aban=8, Azar=9, Dey=10,
Bahman=11, Esfand=12. A month must be explicitly present; never reinterpret an
ordinal number, count, proper name, or organization name as a calendar month.

Examples:
- ۱ فروردین ۱۴۰۵ is complete: year 1405, month 1, day 1.
- ٩ آذر ١٤٠٥ is complete: year 1405, month 9, day 9.
- 30 בתיר 1405 is complete: year 1405, month 4, day 30.
- ۳ تیر is incomplete: translate it as Tir 3 and return dates=[].
- تیر ۱۴۰۵ is incomplete: translate it as Tir 1405 and return dates=[].
- בתיר 1405 is incomplete: translate it as Tir 1405 and return dates=[].
- روز سوم سال ۱۴۰۵ lacks a month: translate it as day 3 of 1405 and return dates=[].
- ۳ تا ۵ تیر ۱۴۰۵ is a range: translate it naturally and return dates=[].
- ۳۰ تیر ۱۴۰۵ تا ۵ مرداد ۱۴۰۵ is a range: translate it naturally and return
  dates=[] even though both endpoints contain three components.
- 30.07.2026 and ۲۰۲۶/۰۷/۲۲ are Gregorian and return dates=[].
- ۱۴۰۵ نفر and 1,405 applications are counts and return dates=[]."""


TRANSLATE_INSTRUCTIONS = f"""You translate foreign-language news headlines into English.

Produce a faithful, natural translation of only the provided headline. Preserve every
explicit fact and relationship, including who did what to whom, gender, number,
titles, attribution, uncertainty, dates, quotations, and suffix labels.

Use established English names for known people, places, institutions, historical
events, programs, and systems. Do not translate proper names literally. Reasonable
transliteration variants are acceptable when no established English form exists.

When the headline contains one or more complete dates in the Iranian Solar Hijri
calendar, replace each complete date in the English translation with a placeholder:
DATE_0 for the first date, DATE_1 for the second, and so on in the order they appear.
Add the corresponding Solar Hijri dates to the dates field in the same order. Each
item must contain integer year, month, and day values.

{SOLAR_DATE_OUTPUT_RULES}

Examples:
- 30 Tir 1405: DATE_0 with year 1405, month 4, day 30.
- 3 Tir: translate as Tir 3 with no placeholder and an empty dates list.
- Tir 1405: translate as Tir 1405 with no placeholder and an empty dates list.

Recognize Solar Hijri dates whether their numbers are written with Persian, Arabic,
or Latin digits and whether the month is written as a name or number. Do not convert
Solar Hijri dates to Gregorian dates yourself. Do not use placeholders for Gregorian
dates merely because they are written in Persian. If there is no complete Solar
Hijri date, translate the headline normally and return an empty dates list.

Identify a date as Solar Hijri only when its month or context identifies the Iranian
Solar Hijri calendar, or when an Iranian numeric date uses a Solar Hijri year such
as 1405. Never infer the calendar from the text's language or numeral script alone.
Gregorian, Hebrew, and Islamic Hijri dates are not Solar Hijri dates. For example,
22 ביולי 2026 is Gregorian, י״ז בתמוז תשפ״ו is Hebrew, and 10 Muharram 1448 AH
is Islamic Hijri; none may produce a placeholder or dates item.

Do not paraphrase, summarize, editorialize, explain, or add information. If the
headline is already in English, preserve its wording except for required Solar
Hijri placeholder substitutions."""

SUMMARIZE_INSTRUCTIONS = f"""You summarize political news articles written in \
foreign languages for an English-speaking reader.

Produce:
- summary: at most 3 sentences, written in English.
- references: short excerpts quoted exactly from the article in its original \
language that support the summary. Do not translate these.
- references_for_translation: copies of references in the same order, with complete
Iranian Solar Hijri dates replaced by ordered placeholders as described below.
- references_dates: one list per reference containing the complete Solar Hijri
dates replaced in that item of references_for_translation.
- tags: every tag that applies, chosen only from: \
{", ".join(get_args(ALLOWED_TAGS))}
- dates: every complete Iranian Solar Hijri date included in the summary, ordered
to match its DATE_0, DATE_1, and subsequent placeholders.

{SOLAR_DATE_OUTPUT_RULES}

When the summary includes a complete Iranian Solar Hijri date, replace the entire
date in the summary with DATE_0 for the first date, DATE_1 for the second, and so
on in the order they appear in the summary. Add exactly one corresponding item to
the dates field for each placeholder at the same index. Each item must contain the
date's explicit integer year, numeric month, and day. The summary must contain
exactly one matching DATE_<index> placeholder for every item in dates; never
return a date item while leaving its raw Solar Hijri date in the summary.

In the English summary, always transliterate incomplete Solar Hijri month names
and render their supplied numbers with Latin digits. For example, write ۵ مرداد
as Mordad 5. This changes only the script, not the date's precision, and must not
create a placeholder or date item.

Recognize Solar Hijri dates whether their numbers use Persian, Arabic, or Latin
digits and whether the month is written as a name or number. Do not calculate or
write the Gregorian equivalent yourself. Do not create placeholders for Gregorian
dates or incomplete dates. If the summary contains no complete Solar Hijri date,
return an empty dates list.

Identify a date as Solar Hijri only when its month or context identifies the Iranian
Solar Hijri calendar, or when an Iranian numeric date uses a Solar Hijri year such
as 1405. Never infer the calendar from the article's language or numeral script
alone. Gregorian, Hebrew, and Islamic Hijri dates are not Solar Hijri dates. These
rules apply equally to summary dates and reference dates.

Counterexamples that must not produce placeholders, dates, or references_dates:
- 22 ביולי 2026 is a Gregorian date written in Hebrew.
- י״ז בתמוז תשפ״ו is a Hebrew-calendar date.
- July 30, 2026 and ۲۲ ژوئیه ۲۰۲۶ are Gregorian dates.
- 10 Muharram 1448 AH is an Islamic Hijri date, not Solar Hijri.

References must remain exact original-language excerpts. Do not replace, translate,
or otherwise alter dates inside references. Every reference must be a literal
substring of the supplied article. If the article is in English, its references
must remain in English; never translate or rewrite them into another language.

Create references_for_translation by copying every item from references in the same
order. In these copies only, replace each complete Iranian Solar Hijri date with
DATE_0, DATE_1, and subsequent placeholders in their natural reading order. Treat
each reference independently. After finishing one reference, reset the placeholder
counter before processing the next reference. Leave every incomplete expression,
range, and non-Solar date exactly unchanged in the copy; do not transliterate
partial dates there.

references_dates must contain exactly one inner list for every item in references,
in the same order. Within each inner list, add exactly one Solar Hijri date for each
placeholder in the matching references_for_translation item. Order the dates to
match DATE_0, DATE_1, and subsequent placeholders, and store each date using its
explicit integer year, numeric month, and day. Use an empty inner list when that
reference contains no complete Solar Hijri date. Leave incomplete, ranged,
ambiguous, Gregorian, Hebrew, and Islamic Hijri dates unchanged in reference
copies for the downstream translator. Every date item must have one matching
placeholder in its reference copy, and every placeholder must have one matching
date item.
If there are no references, both reference lists and references_dates must be empty.

Example: if three references each contain exactly one Solar Hijri date, all three
items in references_for_translation must use DATE_0, not DATE_0, DATE_1, and DATE_2:
- references_for_translation: ["... DATE_0 ...", "... DATE_0 ...", "... DATE_0 ..."]
- references_dates: [[first date], [second date], [third date]]

Mixed-precision examples:
- For "۳ تیر ... مرداد ۱۴۰۵", write "Tir 3 ... Mordad 1405" in the English
  summary, keep both expressions unchanged in references_for_translation, and
  return dates=[] and an empty inner references_dates list. Neither expression
  supplies all three components.
- For "۳۰ تیر ۱۴۰۵ ... ۵ مرداد", replace only the complete first expression:
  write "DATE_0 ... Mordad 5" in the summary, return only year 1405, month 4,
  day 30 in dates, replace only the first expression with DATE_0 in its reference
  copy, and include only that same complete date in references_dates. Do not use
  1405 from the first expression as the missing year of ۵ مرداد.

If the article cannot be summarized, set summary to 'This article cannot be \
summarized.' and leave references, references_for_translation, references_dates,
tags, and dates empty."""
