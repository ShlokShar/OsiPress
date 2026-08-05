
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

TRANSLATE_INSTRUCTIONS = """You translate foreign-language news headlines into English.

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
item must contain the date's integer year, numeric month, and day. For example,
30 Tir 1405 must appear as DATE_0 in the translated headline, with year 1405,
month 4, and day 30 in the first date item.

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
headline is already in English, repeat it unchanged."""

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

When the summary includes a complete Iranian Solar Hijri date, replace the entire
date in the summary with DATE_0 for the first date, DATE_1 for the second, and so
on in the order they appear in the summary. Add exactly one corresponding item to
the dates field for each placeholder at the same index. Each item must contain the
date's integer year, numeric month, and day. For example, if the summary would
include 30 Tir 1405, write DATE_0 in the summary and add year 1405, month 4, and
day 30 as the first dates item.

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
or otherwise alter dates inside references.

Create references_for_translation by copying every item from references in the same
order. In these copies only, replace each complete Iranian Solar Hijri date with
DATE_0, DATE_1, and subsequent placeholders in their natural reading order. Treat
each reference independently. After finishing one reference, reset the placeholder
counter before processing the next reference. Therefore, never use DATE_1 in a
reference unless that same reference contains at least two complete Solar Hijri
dates. Never continue placeholder numbering from a previous reference.

references_dates must contain exactly one inner list for every item in references,
in the same order. Within each inner list, add exactly one Solar Hijri date for each
placeholder in the matching references_for_translation item. Order the dates to
match DATE_0, DATE_1, and subsequent placeholders, and store each date using an
integer year, numeric month, and day. Use an empty inner list when that reference
contains no complete Solar Hijri date. Do not replace Gregorian or incomplete dates.
If there are no references, both reference lists and references_dates must be empty.

Example: if three references each contain exactly one Solar Hijri date, all three
items in references_for_translation must use DATE_0, not DATE_0, DATE_1, and DATE_2:
- references_for_translation: ["... DATE_0 ...", "... DATE_0 ...", "... DATE_0 ..."]
- references_dates: [[first date], [second date], [third date]]

If the article cannot be summarized, set summary to 'This article cannot be \
summarized.' and leave references, references_for_translation, references_dates,
tags, and dates empty."""
