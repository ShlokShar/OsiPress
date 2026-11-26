# OsiPress redesign: implementation handoff

This folder is the source of truth for the OsiPress redesign. It holds every page design (desktop and mobile), the logo files, the design tokens, and this spec. Implement the designs inside the existing OsiPress codebase and stack. Do not replace the stack.

## What's in here

| Path | What it is |
|---|---|
| `pages/desktop/*.dc.html` | Desktop page designs: Homepage, Today, Today-Compare, Event-detail, Archive, Search |
| `pages/mobile/*-mobile.dc.html` | The same six pages designed at 390px wide |
| `pages/Logo-directions.dc.html` | Logo exploration sheet, reference only, not a page to build |
| `brand/` | Final logo files: wordmark, mark, favicons, app icons |
| `tokens/tokens.css` | Colours, fonts and layout constants as CSS custom properties |

### How to read the `.dc.html` files

They come from a design tool and are not production code. Use them as an exact visual and behavioural reference.

- Markup between `<x-dc>` and `</x-dc>` is the page. Styles are inline. Copy the exact values: colours, font sizes, line heights, paddings, gaps, borders.
- `{{name}}` is a template hole, `<sc-for list=… as=…>` is a loop, and `<sc-if value=…>` is a conditional. Translate these into the site's own templating or components.
- The `<script type="text/x-dc">` block at the bottom holds mock data and the interaction logic, such as the compare picker, filters, search highlighting and the globe. Read it to understand the behaviour, then reimplement it against real data.
- Do not ship the mock data, `support.js`, the `<helmet>` tags or the `/_blob/…` script URL.
- Headlines, counts and outlet positions in the mocks are placeholders. Real content comes from the backend.

## Design system

Use `tokens/tokens.css`. The key rules:

- **Palette.** The deep teal `#0A2F36` is the header, footer and dark-section ground. The page ground is `#EEF1F3`, surfaces are white, and ink is `#14191F`. Mint `#7FD1C8` is the only accent on dark backgrounds, and teal `#0B6570` is the link colour on light backgrounds. Each country has a fixed identity colour. Never reuse a country colour for anything else, and never pick colours by rank.
- **Type.** Newsreader for headlines, English translations, event titles and big numbers. Inter for UI, metadata and body copy. Vazirmatn for Persian and Arabic originals, Noto Sans Hebrew for Hebrew, and Inter for Cyrillic and Turkish.
- **Originals.** Always set `lang` and `dir` on the element (`dir="rtl"` for fa, ar and he), use `text-align: start`, and keep originals smaller and greyer than the English. English is the primary line and the original is secondary.
- **No AI tropes.** No gradients (the only allowed effect is the soft shadow on the floating cards on the homepage), no rounded card stacks, no pill overload, no monospace, and no "·" separators or uppercase kicker labels in content.
- **Hit targets** are at least 44px, including on desktop controls.
- **Reduced motion.** With `prefers-reduced-motion`, turn off the globe spin, the ticker, the pulsing pins and the dashed arcs.

## Logo

- `brand/wordmark-on-dark.svg` and `wordmark-on-light.svg` are the primary logo, used in every header and footer. The wordmark reads "[osi]press": the brackets and the quote mark that replaces the dot of the i are in the accent colour. The files are outlined paths, so no font is needed.
- `brand/mark-on-dark.svg` and `mark-on-light.svg` are the symbol, the refined ["], used where only a small square fits.
- `brand/favicon.svg`, `favicon-16/32/48.png`, `apple-touch-icon.png` (180px) and `icon-512.png` are the favicon and app icons, with the mark on teal.
- The header wordmark matches 34px Newsreader text on desktop (about 30px tall) and 28px on mobile. It links to the homepage and its accessible name is "OsiPress".
- The pages render the wordmark with live text and a positioned quote glyph. Use the SVG files instead.

## Global layout

- **Header.** It's identical on every page: teal `#0A2F36` with a 1px `#1E4E57` bottom rule. It's 80px tall on desktop with the wordmark on the left and the nav on the right: About, Today, Archive, Search, 14px Inter, 32px gaps. The current page is white, weight 600, with a 3px mint underline. Today stays active on the Event detail page.
- **Mobile header.** It's 64px tall, with the wordmark and a 44px menu button. The menu opens a full-width list of 56px rows in Newsreader 24px, and the current page shows "You are here".
- **Container.** Max width 1344px, with 48px side padding on desktop and 20px on mobile.
- **Breakpoint.** Switch to the mobile layouts at 768px and below. The mobile designs are not squeezed desktop pages: several components change shape. They are listed per page below.

## Data the designs assume

Make sure the backend exposes these, or flag the ones it doesn't:

- **Outlet:** `name`, `native_name`, `country`, `lean` (1–5 on that country's own axis), `lean_label`.
- **Country:** `key`, `name`, `native_name`, `colour`, `axis_left_label`, `axis_right_label`, five position labels, and a `status` of live or coming next.
- **Article:** `outlet`, `published_at` (UTC, plus local display time and city), `headline_original`, `headline_en`, optional `subhead_original` and `subhead_en`, `url`, `event_id`, `topic`, `edition` (morning or evening).
- **Event:** `id`, `title`, its articles, and derived counts (articles, outlets, countries).

## Page specs

### Today (`Today.dc.html`, `Today-Compare.dc.html`, mobile versions)

- Events are ranked by coverage breadth: the most countries first, then the most outlets, then the newest article.
- The featured white lead treatment is only applied when the top event clearly leads. Suggested rule: it covers at least 2 countries and has more outlets than the next event. Otherwise every event uses the regular style.
- **One article per outlet in the overview.** Show only each outlet's newest article, by `published_at`. Undated articles rank after dated ones.
  - The header shows the full count, e.g. "20 articles from 15 outlets in 6 countries".
  - Outlets that have more articles show a quiet "+N earlier" link.
  - There is no inline expansion. "View all N articles →" goes to Event detail.
- **Spectrum view.** Each country is a row with its colour rule, its name in English and its own script, and its counts. The row has five columns from the left end of the axis to the right, with articles placed by `lean`. Empty slots say "No coverage".
- **Compare countries.** A switch toggles between Spectrum and Compare countries. Compare lets you pick up to 3 countries (the rest are disabled once 3 are picked) and shows them as columns.
  - Each column has its colour rule, a coverage bar showing which of the 5 positions covered the story, and its articles ordered along the axis.
  - Each article shows the outlet, a 5-tick position marker with its label, the English headline, and the original underneath.
  - Columns are never aligned position-to-position across countries, because the axes mean different things in different countries.
- **Originals switch.** There's an optional switch to hide the original-language lines.
- **Mobile.** The top of the page has a "One country / Compare two" switch and a sideways-scrolling row of country buttons.
  - Each event shows a coverage bar per selected country, then that country's articles.
  - A country with no articles for an event shows "No coverage from {country} for this event."

### Event detail (`Event-detail.dc.html`, mobile version)

- It opens with "← Today", the title, the full counts, and "Grouped by country, then outlet, newest first."
- **All countries view.** A country jump bar with counts sits above the country sections. Within each country, outlets are ordered by `lean`, and each outlet's articles are listed newest first.
- When an outlet has more than one article, its newest is labelled "Shown on overview".
- **Compare countries** works the same as on Today: up to 3 countries as columns, with outlets and their articles inside each column.
- **Mobile.** A "Coverage at a glance" table shows every country's coverage bar and count, and tapping a row filters to that country. The country buttons ("All" plus any mix) stick to the top as you scroll, and each outlet is a white card.
- Carry the overview's country selection through to this page, and into the URL so a comparison can be shared.

### Homepage (`Homepage.dc.html`, mobile version)

- **Hero.** Dark teal background with the copy exactly as in the design and the mint "Read today's articles →" button.
- **The globe** is interactive.
  - Build it with `d3-geo` (orthographic projection with `clipAngle(90)`) and `world-atlas` `countries-110m.json` via `topojson-client`.
  - Highlight the live countries (Iran 364, Israel 376) in mint, and coming-next countries (Russia 643, Ukraine 804) in `#2E7782`.
  - Pin today's events. Dashed arcs run from each live country's capital to each pin.
  - It auto-rotates about 0.24°/s and redraws at about 30fps. It pauses on hover, can be dragged to rotate, and turns to centre a pin or list item when clicked.
  - Skip countries on the far side of the globe before projecting, for performance.
  - With reduced motion, show a static globe.
  - Today's events come from the same data as the Today page.
- **"On the globe this evening"** lists today's events as buttons that sync with the pins, and a white card shows the selected event with one headline per country.
- **Ticker.** A band of original-language headlines with their English underneath. It loops with CSS and pauses on hover.
- **June 20 example.** Static editorial content.
- **Spectrum explorer.** Country tabs, with countries marked "Coming next" where relevant. The axis shows outlets as dots, and switching country animates the dots to their new positions. Hovering or clicking an outlet shows a card with its native name, position and today's headline.
  - On mobile, the axis becomes vertical rows, each with a mini track.

### Archive (`Archive.dc.html`, mobile version)

- **Filters.** Country buttons ("Pick one country, or two to compare"), with countries that aren't live yet shown disabled and dashed. A range switch offers Last 30 days, Last 90 days and Since launch.
- **Chart.** Articles per day, with Iran above a centre axis and Israel mirrored below in its chart colour (`#11825A` passes colour-blind checks against Israel blue).
  - Each day is a full-height button. Hovering shows a dark tooltip with the counts and the top story; clicking loads that day in the list.
  - Big spikes get a direct label.
  - On mobile, the tooltip becomes a static card under the chart and the default range is 30 days.
- **Other sections.** The Topics list has counts and filters the page. "Latest days" groups events by day, and each event shows a per-country coverage strip and links to its event page. "Most covered" lists the top 5 events by volume.
  - That last one is a product question, because the site states that OsiPress doesn't rank coverage.

### Search (`Search.dc.html`, mobile version)

- **It opens empty.** Only run a query when the user submits, or after typing has paused for at least 300ms. Never query on every keystroke.
- **Matching** covers the English translation, the original headline (so Persian and Hebrew work), the outlet and the event title. Highlight the match in the English headline with a `<mark>`.
- **Results**
  - Summary: the query, then "N articles from M outlets, first date to last date".
  - Country toggles and a Newest/Oldest sort.
  - "When it was written about": monthly bars per country.
  - "Who wrote about it": each country's 5 positions with every outlet and its match count; zero-match outlets stay visible.
  - Result list: outlet, position marker, date, highlighted English, original, "Part of [event]", "Read original".
- **Empty states** cover both no query and no results.

## Not settled yet

- **Outlet positions.** The `lean` values and outlet lists in the mocks are approximations. Use the real OsiPress classification.
- **Placeholder content.** The Russia and Ukraine outlets and headlines in the mocks are placeholders until those countries launch.
- **Footer wording.** It says "Translations are machine-generated…", replacing the old "Summaries are AI-generated".
- **"Most covered"** on the Archive page versus the "doesn't rank coverage" statement.
- **"All today" and "Methodology".** They were removed from the main nav. Put a Top stories / All today switch on the Today page and Methodology in the footer.

## How to work through this

1. Read this file, `tokens/tokens.css` and the repo's existing templates and routes. Then propose a short plan that maps each design page to the templates or components it touches.
2. Build the shared parts first: tokens, header, footer, logo files and favicons, then the shared components (country button, segmented control, 5-tick position marker, coverage bar, article block, event block).
3. Build one page at a time in this order: Today, Event detail, Homepage, Archive, Search. Do desktop and mobile for each before moving on.
4. After each page, run the site locally, take desktop (1440px) and mobile (390px) screenshots, and compare them with the design files. Fix the differences before moving to the next page.
