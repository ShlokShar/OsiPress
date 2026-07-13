# OsiPress

Snapshots of what foreign press are telling their own people, 
translated to English and shown side by side. Prototype pair: Iran and Israel.

## Problem

When you read about a foreign conflict, the reporting usually comes from 
outlets in your own country. If you’ve followed the Iran–Israel war, you’ve 
probably read dozens of articles *about* Iran and very few *from* Iran.

Iranian and Israeli outlets publish for domestic audiences in Persian and 
Hebrew, often framing events differently from their international editions. 
Unless you read those languages, directly comparing that coverage is difficult.

## What is OsiPress?

OsiPress (_Open Source Info Press_) shows what different countries' presses 
are telling their own citizens. Right now it covers Iran and Israel through 
six outlets:

- **Iran** (Persian editions): Kayhan (right), Hamshahri (center), Shargh (left)
- **Israel** (Hebrew editions): Israel Hayom (right-leaning), Yedioth 
  Ahronoth (centrist), Haaretz (left-leaning)

Twice a day, OsiPress checks each outlet’s most recent articles. Each 
article includes:

- a verbatim English translation of the headline
- a two-sentence summary
- quotes from the article in the original language to back up the summary
- a link to the original article

Articles live on permanent dated URLs, so over time the site becomes a 
day-by-day archive of what each side was told.

Here are article comparisons from June 20, 2026, the day Iran declared the 
Strait of Hormuz (the channel a fifth of the world's oil ships through) 
closed again:

> **Tasnim, carrying the IRGC announcement (Persian):** "In response to the 
> ceaseless violations of the ceasefire by the Zionist regime in southern 
> Lebanon... the Strait of Hormuz will be closed to vessel traffic."
>
> **Israel Hayom (Hebrew):** "IDF encircles dozens of Hezbollah terrorists 
> in southern Lebanon, Iran threatens to block the Strait of Hormuz."

In the Iranian telling, Israel broke a ceasefire, so the strait is now 
closed. In the Israeli telling, the army is rounding up terrorists, and the 
closure is just a threat. Neither headline is technically lying. They start the 
story at different points, and each skips the part that complicates its own 
side. OsiPress won't tell you which telling is right. It puts them next to 
each other, so you can notice the difference on your own.

[Iranian statement](https://www.iribnews.ir/fa/news/5831029/) · [Israel 
Hayom, June 20, 2026](https://www.israelhayom.co.il/news/article/20803192)

## Architecture / Application Design

The architecture is split into two parts: the  script that collects articles 
and the Flask app that displays them.

The script runs twice a day. It:

1. reads each source's RSS feed
2. uses a light weight OpenAI model to filter for political relevancy
3. extracts the text from each article with Trafilatura
4. translates the headline into English
5. creates a short summary with supporting quotes
6. saves everything to PostgreSQL

Each article is processed separately, so one broken feed or article should not 
stop the other sources from being collected. Article URLs and redirects are 
also checked before they are downloaded.

The Flask application reads the latest collection for each source from the 
database. `/today` displays the most recent articles, while `/archive` lets the 
user view a previous date. If today's collection is empty, the website can fall 
back up to three days instead of showing a blank page.

In production, the Flask application runs through Gunicorn behind Nginx. A 
systemd timer runs the ingestion script at 06:00 and 18:00 UTC.

```text
RSS feeds -> ingestion script -> PostgreSQL -> Flask -> Gunicorn -> Nginx
```

## Replicate

You will need Python 3.11+, PostgreSQL, and an OpenAI API key.

First, clone the repository and install the dependencies:

```bash
git clone https://github.com/ShlokShar/OsiPress.git
cd OsiPress

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a PostgreSQL user and database:

```sql
CREATE USER osipress WITH PASSWORD 'your_password';
CREATE DATABASE osipress OWNER osipress;
```

Create a `.env` file in the root of the project and fill in these fields:

```env
DATABASE_URL=postgresql://osipress:your_password@localhost:5432/osipress
OPENAI_API_KEY=your_openai_api_key
```

Create the database tables:

```bash
python -c "from shared.database import Base, engine; import shared.models; Base.metadata.create_all(engine)"
```

Then add the countries and sources expected by `cron/sources.json`. Feel 
free to change the sources to desired RSS feeds:

```sql
INSERT INTO countries (name) VALUES ('Iran'), ('Israel');

INSERT INTO sources (country_id, name, link, political_leaning)
SELECT id, 'Shargh', 'https://www.sharghdaily.com/feeds/', 'Left'
FROM countries WHERE name = 'Iran';

INSERT INTO sources (country_id, name, link, political_leaning)
SELECT id, 'Hamshahri', 'https://www.hamshahrionline.ir/rss/pl/402', 'Center'
FROM countries WHERE name = 'Iran';

INSERT INTO sources (country_id, name, link, political_leaning)
SELECT id, 'Kayhan', 'https://kayhan.ir/fa/rss/allnews', 'Right'
FROM countries WHERE name = 'Iran';

INSERT INTO sources (country_id, name, link, political_leaning)
SELECT id, 'Haaretz', 'https://www.haaretz.co.il/srv/htz---all-articles', 'Left'
FROM countries WHERE name = 'Israel';

INSERT INTO sources (country_id, name, link, political_leaning)
SELECT id, 'Yedioth Ahronoth',
       'https://www.ynet.co.il/Integration/StoryRss2.xml', 'Center'
FROM countries WHERE name = 'Israel';

INSERT INTO sources (country_id, name, link, political_leaning)
SELECT id, 'Israel Hayom', 'https://www.israelhayom.co.il/rss/rss.xml', 'Right'
FROM countries WHERE name = 'Israel';
```

Run the ingestion script once to collect articles:

```bash
python -m cron.script
```

Finally, start the website:

```bash
flask --app main run
```

The landing page will be available at `http://127.0.0.1:5000`, with the latest 
collection at `/today` and previous collections at `/archive`.
