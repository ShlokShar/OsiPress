# Osipress

Snapshots of what foreign front pages are telling their own people, 
translated to English and shown side by side. Prototype pair: Iran and Israel.

## Problem

When you read about a foreign conflict, who's writing it? Outlets from your 
home country. If you've followed the Iran-Israel war at all, you've 
probably read dozens of articles *about* Iran and probably zero *from* Iran.

Both countries have a domestic press that publishes every morning for its 
own people, Iranian papers in Persian, Israeli papers in Hebrew. What they 
tell their own readers is often different from what their English editions 
tell the world, and unless you read the language, you never see any of it.

So if you want to know what Iranian papers told Iranians this morning, or 
what Israeli papers told Israelis, there's no easy way to do it.

## What is Osipress?

Osipress (_Open Source Info Press_) shows what different countries' presses 
are telling their own citizens. Right now it covers Iran and Israel through 
six outlets:

- **Iran** (Persian editions): Kayhan (hardline), Tasnim (IRGC-linked), 
  Etemad (reformist)
- **Israel** (Hebrew editions): Israel Hayom (right-leaning), Ynet (centrist)
  , Haaretz (left-leaning)

Two times a day, Osipress looks at each outlet's front page and takes 
whatever story its editors put on top. For each article there is:
- the headline is translated verbatim: when an Iranian paper writes 
  "the Zionist regime," that renders, and when an Israeli paper writes "the 
  Ayatollah regime," that renders too
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
side. Osipress won't tell you which telling is right. It puts them next to 
each other, so you can notice the difference on your own.

[Iranian statement](https://www.iribnews.ir/fa/news/5831029/) · [Israel 
Hayom, June 20, 2026](https://www.israelhayom.co.il/news/article/20803192)

## Architecture / Application Design

## Replicate
