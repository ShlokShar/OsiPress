"""Fill a development database with content for the redesign prototype.

The redesign needs five and a half months of archive history, several events a
day and multiple articles per outlet before any of its pages can be judged.
This script writes that through the real tables, so the site renders over the
normal query path instead of a fixture branch inside the app.

It only inserts, and stops if the tables already hold rows. `--top-up` adds
the days since the newest run so the prototype keeps showing a populated
Today, and clearing everything first takes an explicit `--reset`. Every path
refuses to touch a database whose name does not end in `_dev`.

    python scripts/seed_prototype.py
    python scripts/seed_prototype.py --top-up
    python scripts/seed_prototype.py --reset
    python scripts/seed_prototype.py --database-url postgresql:///osipress_dev
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from sqlalchemy import func, text

from shared.countries import COUNTRIES, OUTLETS
from shared.database import session_factory
from shared.models import (
    ArticleAppearances,
    ArticleEvents,
    Articles,
    Countries,
    Events,
    IngestionRuns,
    Sources,
    Topics,
)

LAUNCH = date(2026, 7, 9)
EVENING_FROM_HOUR = 6
LAST_PUBLISH_HOUR = 15

TOPIC_NAMES = (
    "Nuclear programme",
    "Lebanon and Hezbollah",
    "Gaza",
    "Economy and energy",
    "Shipping and the Gulf",
    "Domestic politics",
    "Regional diplomacy",
)

TOPIC_DESCRIPTIONS = {
    "Nuclear programme": "Enrichment, inspections and the agreements around them.",
    "Lebanon and Hezbollah": "The Lebanese front, disarmament and the border mechanism.",
    "Gaza": "The war, the ceasefire phases and humanitarian access.",
    "Economy and energy": "Currencies, budgets, oil and sanctions pressure.",
    "Shipping and the Gulf": "The Strait of Hormuz, tankers and naval activity.",
    "Domestic politics": "Parliaments, coalitions, protests and public services.",
    "Regional diplomacy": "Mediation, envoys and talks between capitals.",
}

# Outlet feed-or-homepage links. The six outlets in cron/sources.json keep
# their real feeds; the rest are seeded so the five-position spectrum has
# something in every slot.
SOURCE_LINKS = {
    "Shargh": "https://www.sharghdaily.com/feeds/",
    "Hamshahri": "https://www.hamshahrionline.ir/rss/pl/402",
    "Kayhan": "https://kayhan.ir/fa/rss/allnews",
    "Etemad": "https://www.etemadnewspaper.ir/",
    "Donya-e-Eqtesad": "https://www.donya-e-eqtesad.com/",
    "Javan": "https://www.javanonline.ir/",
    "Tasnim": "https://www.tasnimnews.com/",
    "Fars": "https://www.farsnews.ir/",
    "Haaretz": "https://www.haaretz.co.il/srv/htz---all-articles",
    "Yedioth Ahronoth": "https://www.ynet.co.il/Integration/StoryRss2.xml",
    "Israel Hayom": "https://www.israelhayom.co.il/rss/rss.xml",
    "Globes": "https://www.globes.co.il/",
    "Maariv": "https://www.maariv.co.il/",
    "Makor Rishon": "https://www.makorrishon.co.il/",
}

COUNTRY_OF_OUTLET = {
    "Shargh": "Iran",
    "Etemad": "Iran",
    "Hamshahri": "Iran",
    "Donya-e-Eqtesad": "Iran",
    "Javan": "Iran",
    "Kayhan": "Iran",
    "Tasnim": "Iran",
    "Fars": "Iran",
    "Haaretz": "Israel",
    "Yedioth Ahronoth": "Israel",
    "Globes": "Israel",
    "Maariv": "Israel",
    "Israel Hayom": "Israel",
    "Makor Rishon": "Israel",
}

LEANING_LABELS = {1: "Left", 3: "Center", 4: "Center-right", 5: "Right"}

# (outlet, hour, original headline, English headline, original subhead,
#  English subhead)
TODAY_EVENTS = (
    (
        "Nuclear programme",
        "IAEA Board of Governors weighs a new resolution on Iran",
        (
            ("Etemad", 3, "پیش از قطعنامه، فرصت دیپلماسی را از دست ندهیم",
             "Before the resolution, let’s not lose the window for diplomacy",
             "کارشناسان: همکاری فنی با آژانس تنها راه جلوگیری از ارجاع پرونده به شورای امنیت است",
             "Experts: technical cooperation with the Agency is the only way to keep the file from being referred to the Security Council"),
            ("Kayhan", 2, "قطعنامه شورای حکام؛ اروپا باز هم بر طبل فشار می‌کوبد",
             "Board of Governors resolution: Europe beats the drum of pressure again",
             "تروئیکای اروپایی مجری سیاست‌های آمریکا و رژیم صهیونیستی در وین",
             "The European troika is carrying out the policies of America and the Zionist regime in Vienna"),
            ("Kayhan", 22, "سکوت آژانس در برابر تهدیدهای اسرائیل",
             "The Agency’s silence in the face of Israel’s threats", "", ""),
            ("Javan", 4, "پاسخ ایران به قطعنامه، کاهش همکاری با آژانس است",
             "Iran’s answer to a resolution is reduced cooperation with the Agency",
             "نماینده مجلس: هر اقدام خصمانه با واکنش متقابل روبه‌رو می‌شود",
             "MP: any hostile action will be met with a reciprocal response"),
            ("Haaretz", 3, "ישראל לוחצת על אירופה לגנות את איראן, אבל בוושינגטון מעדיפים לחכות",
             "Israel presses Europe to condemn Iran, but Washington prefers to wait",
             "גורמים מדיניים: הממשל האמריקאי חושש שהחלטה חריפה תדחוף את טהרן להאיץ את ההעשרה",
             "Diplomatic sources: the US administration fears a harsh resolution will push Tehran to accelerate enrichment"),
            ("Haaretz", 23, "הדיפלומטים בווינה: הרוב להחלטה מובטח",
             "Diplomats in Vienna: a majority for the resolution is assured", "", ""),
            ("Yedioth Ahronoth", 4, "מועצת הנגידים מתכנסת: מה יקרה אם איראן תגיב בהעשרה?",
             "The Board of Governors convenes: what happens if Iran responds with enrichment?",
             "כל התרחישים: מהחלטת גינוי ועד חזרה למועצת הביטחון",
             "Every scenario, from a censure resolution to a return to the Security Council"),
            ("Israel Hayom", 4, "הזדמנות אחרונה לעצור את הגרעין האיראני",
             "A last chance to stop the Iranian nuclear programme",
             "בכיר ישראלי: ״אם אירופה תהסס, ישראל תשקול את צעדיה״",
             "Senior Israeli official: “If Europe hesitates, Israel will weigh its steps”"),
            ("Israel Hayom", 9, "ירושלים מעבירה לאירופה מידע מודיעיני חדש",
             "Jerusalem passes new intelligence to Europe", "", ""),
        ),
    ),
    (
        "Lebanon and Hezbollah",
        "Pressure mounts on Beirut over Hezbollah disarmament",
        (
            ("Shargh", 3, "لبنان میان فشار آمریکا و ملاحظات داخلی",
             "Lebanon caught between American pressure and domestic considerations", "", ""),
            ("Tasnim", 5, "حزب‌الله: سلاح مقاومت قابل مذاکره نیست",
             "Hezbollah: the resistance’s weapons are not negotiable", "", ""),
            ("Tasnim", 10, "تحرکات نظامی رژیم صهیونیستی در مرز لبنان",
             "Zionist regime military movements on the Lebanese border", "", ""),
            ("Haaretz", 6, "ממשלת לבנון מבקשת עוד זמן לפירוק חיזבאללה",
             "Lebanon’s government asks for more time to disarm Hezbollah", "", ""),
            ("Maariv", 5, "צה״ל נערך לסבב נוסף בצפון",
             "The IDF prepares for another round in the north", "", ""),
        ),
    ),
    (
        "Economy and energy",
        "Oil slides below $60 a barrel",
        (
            ("Donya-e-Eqtesad", 3, "نفت زیر ۶۰ دلار؛ بودجه ۱۴۰۶ زیر فشار",
             "Oil below $60: the 1406 budget under pressure", "", ""),
            ("Fars", 6, "تحریم‌ها نتوانسته صادرات نفت ایران را متوقف کند",
             "Sanctions have failed to halt Iran’s oil exports", "", ""),
            ("Globes", 7, "מחיר הנפט צונח: מה זה אומר על הכלכלה האיראנית",
             "The oil price plunges: what it means for Iran’s economy", "", ""),
            ("Makor Rishon", 6, "הנפט הזול מחליש את טהרן",
             "Cheap oil weakens Tehran", "", ""),
        ),
    ),
)

# Earlier-day material. Each entry is a topic, an event title and its
# articles as (outlet, original, English).
HISTORY_EVENTS = (
    ("Shipping and the Gulf", "Naval drills disrupt traffic near Hormuz", (
        ("Kayhan", "رزمایش دریایی سپاه در تنگه هرمز", "IRGC naval exercise in the Strait of Hormuz"),
        ("Fars", "نیروی دریایی آمادگی خود برای دفاع از هرمز را نشان داد", "Navy shows its readiness to defend Hormuz"),
        ("Tasnim", "تنگه هرمز زیر نظر کامل نیروهای ایرانی است", "The Strait of Hormuz is under full Iranian watch"),
        ("Israel Hayom", "איראן מפגינה כוח במיצר הורמוז", "Iran flexes its muscles in the Strait of Hormuz"),
        ("Yedioth Ahronoth", "מיצר הורמוז: מה המשמעות לישראל", "The Strait of Hormuz: what it means for Israel"),
        ("Globes", "חברות הביטוח הימי נסוגות מהמפרץ", "Shipping insurers pull back from the Gulf"),
    )),
    ("Economy and energy", "Rial falls to a new low against the dollar", (
        ("Hamshahri", "دلار از مرز ۱۲۰ هزار تومان گذشت", "The dollar passes 120,000 tomans as the rial slides"),
        ("Shargh", "سقوط ریال و نگرانی بازار", "The rial’s fall and an anxious market"),
        ("Donya-e-Eqtesad", "بازار ارز در انتظار تصمیم بانک مرکزی", "The currency market waits on the central bank"),
        ("Globes", "הריאל האיראני צונח לשפל חדש", "The Iranian rial plunges to a new low"),
    )),
    ("Nuclear programme", "IAEA inspectors return to Isfahan", (
        ("Shargh", "بازگشت بازرسان آژانس؛ فرصتی برای کاهش تنش", "The inspectors’ return: a chance to ease tension with the Agency"),
        ("Etemad", "همکاری با آژانس از سر گرفته شد", "Cooperation with the Agency resumes"),
        ("Yedioth Ahronoth", "פקחי סבא״א לא יחזרו לאיראן בקרוב", "IAEA inspectors won’t be back in Iran any time soon"),
        ("Haaretz", "ישראל עוקבת אחר הפקחים באיספהאן", "Israel is watching the inspectors in Isfahan"),
    )),
    ("Lebanon and Hezbollah", "Israeli strikes hit targets in southern Lebanon", (
        ("Tasnim", "حملات رژیم صهیونیستی به جنوب لبنان", "Zionist regime strikes on southern Lebanon"),
        ("Shargh", "جنوب لبنان زیر آتش؛ بیروت خواستار مداخله شد", "Southern Lebanon under fire as Beirut calls for intervention"),
        ("Haaretz", "הפסקת האש בלבנון מתערערת כשחיזבאללה מתחמש מחדש", "The Lebanon ceasefire is fraying as Hezbollah rearms"),
        ("Maariv", "תקיפות בדרום לבנון: סיכום הלילה", "Strikes in southern Lebanon: the night in summary"),
        ("Israel Hayom", "צה״ל מכתר עשרות מחבלי חזבאללה בדרום לבנון", "The IDF encircles dozens of Hezbollah fighters in southern Lebanon"),
    )),
    ("Domestic politics", "Water rationing expands across Tehran", (
        ("Hamshahri", "جیره‌بندی آب در تهران گسترش یافت", "Water rationing expands across Tehran"),
        ("Etemad", "بحران آب؛ وعده‌ها و واقعیت", "The water crisis: promises and reality"),
        ("Javan", "مدیریت مصرف آب وظیفه همگانی است", "Managing water use is everyone’s duty"),
    )),
    ("Domestic politics", "Knesset clashes over the draft exemption bill", (
        ("Haaretz", "עימות בכנסת על חוק הגיוס", "Clashes in the Knesset over the draft law"),
        ("Yedioth Ahronoth", "הקואליציה מתפצלת סביב חוק הגיוס", "The coalition splits over the draft law"),
        ("Makor Rishon", "חוק הגיוס: ההסדר שמחכה להכרעה", "The draft law: an arrangement awaiting a decision"),
    )),
    ("Regional diplomacy", "Oman hosts indirect talks", (
        ("Etemad", "مسقط میزبان گفت‌وگوهای غیرمستقیم", "Muscat hosts indirect talks"),
        ("Hamshahri", "تهران برای نشست وین آماده می‌شود", "Tehran prepares for the Vienna meeting"),
        ("Yedioth Ahronoth", "שיחות עקיפות בעומאן: מה על השולחן", "Indirect talks in Oman: what is on the table"),
        ("Globes", "השווקים עוקבים אחרי השיחות בעומאן", "Markets follow the talks in Oman"),
    )),
    ("Gaza", "Ceasefire talks resume in Cairo", (
        ("Shargh", "مذاکرات آتش‌بس در قاهره از سر گرفته شد", "Ceasefire talks resume in Cairo"),
        ("Tasnim", "مقاومت فلسطین شرایط خود را اعلام کرد", "The Palestinian resistance states its conditions"),
        ("Haaretz", "שיחות הפסקת האש מתחדשות בקהיר", "Ceasefire talks resume in Cairo"),
        ("Maariv", "המשלחת הישראלית יוצאת לקהיר", "The Israeli delegation leaves for Cairo"),
    )),
    ("Economy and energy", "Bank of Israel holds interest rates", (
        ("Globes", "בנק ישראל מותיר את הריבית ללא שינוי", "The Bank of Israel leaves rates unchanged"),
        ("Yedioth Ahronoth", "הריבית נותרת: מה זה אומר למשכנתאות", "Rates stay put: what it means for mortgages"),
        ("Donya-e-Eqtesad", "تصمیم بانک مرکزی اسرائیل و بازارهای منطقه", "The Israeli central bank’s decision and regional markets"),
    )),
    ("Shipping and the Gulf", "Iran seizes a tanker in the Gulf of Oman", (
        ("Fars", "توقیف نفتکش متخلف در دریای عمان", "A tanker in violation is seized in the Gulf of Oman"),
        ("Kayhan", "اقتدار دریایی ایران در خلیج فارس", "Iran’s naval authority in the Persian Gulf"),
        ("Israel Hayom", "איראן השתלטה על מכלית במפרץ עומאן", "Iran seized a tanker in the Gulf of Oman"),
        ("Globes", "דמי הביטוח הימי מזנקים אחרי ההשתלטות", "Marine insurance premiums jump after the seizure"),
    )),
)

SUMMARIES = (
    "The report sets out what was decided, who spoke and what the outlet expects to follow.",
    "The piece places the day’s development against the past week of coverage.",
    "Officials quoted in the article disagree on what the next step should be.",
    "The outlet leads on the practical consequences rather than the announcement itself.",
)


class Rnd:
    """Small deterministic generator, so repeated seeds look identical."""

    def __init__(self, seed: int) -> None:
        self.state = seed

    def next(self) -> float:
        self.state = (self.state * 1103515245 + 12345) % (2 ** 31)
        return self.state / (2 ** 31)

    def pick(self, items):
        return items[int(self.next() * len(items)) % len(items)]

    def between(self, low: int, high: int) -> int:
        return low + int(self.next() * (high - low + 1)) % (high - low + 1)


SEEDED_TABLES = (
    "match_log",
    "article_events",
    "events",
    "article_appearances",
    "ingestion_runs",
    "article_urls",
    "articles",
    "sources",
    "topics",
    "countries",
)


def existing_rows(session) -> dict[str, int]:
    """Return the row count of every table this script writes to."""

    counts = {}
    for table in SEEDED_TABLES:
        counts[table] = session.execute(
            text(f"SELECT count(*) FROM {table}")
        ).scalar() or 0
    return {table: count for table, count in counts.items() if count}


def clear(session) -> None:
    for table in SEEDED_TABLES:
        session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
    session.commit()


def last_seeded_day(session) -> Optional[date]:
    """Return the most recent day that already has a published run."""

    newest = session.query(func.max(IngestionRuns.started_at)).scalar()
    return newest.astimezone(timezone.utc).date() if newest else None


def reference_data(session):
    """Get or create the countries, topics and outlets the seed needs."""

    countries = {}
    for key in ("ir", "il"):
        name = COUNTRIES[key]["name"]
        country = session.query(Countries).filter_by(name=name).first()
        if not country:
            country = Countries(name=name)
            session.add(country)
        countries[name] = country
    session.flush()

    topics = {}
    for name in TOPIC_NAMES:
        topic = session.query(Topics).filter_by(name=name).first()
        if not topic:
            topic = Topics(name=name, description=TOPIC_DESCRIPTIONS[name])
            session.add(topic)
        topics[name] = topic
    session.flush()

    sources = {}
    for outlet, (_, position) in OUTLETS.items():
        source = session.query(Sources).filter_by(name=outlet).first()
        if not source:
            source = Sources(
                country_id=countries[COUNTRY_OF_OUTLET[outlet]].id,
                name=outlet,
                link=SOURCE_LINKS[outlet],
                political_leaning=LEANING_LABELS[position],
            )
            session.add(source)
        sources[outlet] = source
    session.flush()

    return countries, topics, sources


def seed(
    session,
    last_day: date,
    reset: bool,
    first_day: Optional[date] = None,
) -> dict:
    if reset:
        clear(session)

    _, topics, sources = reference_data(session)

    rnd = Rnd(20260709)
    counts = {"articles": 0, "events": 0, "runs": 0, "days": 0}
    day = first_day or LAUNCH

    while day <= last_day:
        counts["days"] += 1
        is_today = day == last_day
        if is_today:
            plan = [
                (topic, title, [(o, h, orig, en, so, se)
                                for (o, h, orig, en, so, se) in articles])
                for topic, title, articles in TODAY_EVENTS
            ]
        else:
            plan = []
            used = set()
            for _ in range(rnd.between(2, 3)):
                topic, title, pool = rnd.pick(HISTORY_EVENTS)
                if title in used:
                    continue
                used.add(title)
                take = rnd.between(2, len(pool))
                chosen = list(pool)[:take]
                plan.append((topic, title, [
                    (outlet, rnd.between(0, LAST_PUBLISH_HOUR), orig, en, "", "")
                    for outlet, orig, en in chosen
                ]))

        runs = {}
        for edition, hour in (("morning", 6), ("evening", 16)):
            run = IngestionRuns(
                started_at=datetime.combine(
                    day, datetime.min.time(), tzinfo=timezone.utc
                ) + timedelta(hours=hour),
                status="succeeded",
            )
            run.completed_at = run.started_at + timedelta(minutes=12)
            session.add(run)
            runs[edition] = run
            counts["runs"] += 1
        session.flush()

        slots = {edition: {} for edition in runs}

        for topic, title, articles in plan:
            rows = []
            for outlet, hour, original, english, sub_original, sub_english in articles:
                # A run can only collect what was already published, so keep
                # every article inside the window of the run that picks it up:
                # the 06:00 run takes 00:00-05:59, the 16:00 run 06:00-15:59.
                hour = min(hour, LAST_PUBLISH_HOUR)
                published = datetime.combine(
                    day, datetime.min.time(), tzinfo=timezone.utc
                ) + timedelta(hours=hour, minutes=rnd.between(0, 55))
                edition = "morning" if hour < EVENING_FROM_HOUR else "evening"
                captured = runs[edition].started_at + timedelta(
                    minutes=rnd.between(1, 20)
                )
                summary = sub_english or rnd.pick(SUMMARIES)
                article = Articles(
                    source_id=sources[outlet].id,
                    headline=original,
                    translated_headline=english,
                    link=f"{SOURCE_LINKS[outlet].rstrip('/')}/story/{day.isoformat()}/{counts['articles']}",
                    summary=summary,
                    references_original=[sub_original] if sub_original else [],
                    references_translated=[sub_english] if sub_english else [],
                    tags=[topic],
                    published_at=published,
                    captured_at=captured,
                )
                session.add(article)
                counts["articles"] += 1
                rows.append((article, published, outlet, edition))
            session.flush()

            published_times = [published for _, published, _, _ in rows]
            event = Events(
                topic_id=topics[topic].id,
                title=title,
                status="visible",
                outlet_count=len({outlet for _, _, outlet, _ in rows}),
                article_count=len(rows),
                first_seen=min(published_times),
                last_seen=max(published_times),
                first_published_at=min(published_times),
                titled_at=min(published_times),
            )
            session.add(event)
            session.flush()
            counts["events"] += 1

            for article, published, outlet, edition in rows:
                session.add(ArticleEvents(
                    article_id=article.id,
                    event_id=event.id,
                    joined_at=published + timedelta(minutes=30),
                    match_path="high",
                    match_score=0.82 + rnd.next() / 10,
                ))
                slot = slots[edition].setdefault(sources[outlet].id, [])
                if len(slot) < 3:
                    slot.append(article.id)

        for edition, by_source in slots.items():
            for source_id, article_ids in by_source.items():
                for position, article_id in enumerate(article_ids):
                    session.add(ArticleAppearances(
                        run_id=runs[edition].id,
                        source_id=source_id,
                        article_id=article_id,
                        position=position,
                    ))

        session.commit()
        day += timedelta(days=1)

    return counts


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument(
        "--last-day",
        default=datetime.now(timezone.utc).date().isoformat(),
        help="the most recent day to seed, defaulting to today in UTC",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="empty the seeded tables first instead of stopping",
    )
    parser.add_argument(
        "--top-up",
        action="store_true",
        help="add only the days after the newest run, keeping what is there",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow a database whose name does not end in _dev",
    )
    args = parser.parse_args()

    if not args.database_url:
        print("No database URL: pass --database-url or set DATABASE_URL.")
        return 1

    name = args.database_url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    if not name.endswith("_dev") and not args.force:
        print(
            f"Refusing to seed {name!r}: this script only runs against a "
            f"*_dev database. Pass --force to override."
        )
        return 1

    last_day = date.fromisoformat(args.last_day)
    if last_day < LAUNCH:
        print(f"--last-day must be on or after {LAUNCH.isoformat()}.")
        return 1

    factory = session_factory(args.database_url)
    with factory() as session:
        first_day = None
        if args.top_up and not args.reset:
            seeded_to = last_seeded_day(session)
            if seeded_to is not None:
                first_day = seeded_to + timedelta(days=1)
                if first_day > last_day:
                    print(
                        f"{name} is already seeded to "
                        f"{seeded_to.isoformat()}; nothing to add."
                    )
                    return 0
        elif not args.reset:
            occupied = existing_rows(session)
            if occupied:
                listing = ", ".join(
                    f"{table} ({count})" for table, count in occupied.items()
                )
                print(
                    f"{name} already holds data: {listing}. Nothing was "
                    f"written. Pass --reset to empty these tables and seed "
                    f"from scratch."
                )
                return 1
        counts = seed(session, last_day, args.reset, first_day)

    print(
        f"Seeded {name}: {counts['days']} days, {counts['articles']} articles, "
        f"{counts['events']} events, {counts['runs']} ingestion runs "
        f"({(first_day or LAUNCH).isoformat()} to {last_day.isoformat()})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
