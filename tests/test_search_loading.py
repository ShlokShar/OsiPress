"""Browser tests for the search page's loading skeleton.

The skeleton is client-side only: /search is a synchronous form GET, so the
server is blocked inside hybrid_search() and can never render a loading state.
static/js/search.js conceals the current page content and swaps the skeleton in
while the request is in flight.

That makes it a rendering concern rather than a markup one, so these run in a
real browser. Two regressions here passed static checks and still failed for
users: a DOM mutation that was never painted, and concealment that silently
no-opped because `hidden` loses to an author `display` declaration.

No database and no OpenAI: the search service and the source lookup are both
stubbed, and the stub can be slowed so the in-flight window is observable.

Run from the repo root:
    python -m unittest tests.test_search_loading -v
"""

import threading
import time
import unittest
from datetime import datetime, timezone

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

import main
from shared.models import Articles

HOST = "127.0.0.1"
PORT = 5099
BASE = f"http://{HOST}:{PORT}"

# How long the stubbed search blocks for when a test needs to observe the
# in-flight window. Setup navigations run with no delay to keep the suite fast.
SEARCH_DELAY = 1.5

DESKTOP = {"width": 1280, "height": 800}
MOBILE = {"width": 390, "height": 844}

SOURCES = {
    1: {"outlet": "Haaretz", "political_leaning": "left", "country": "Israel"},
    2: {"outlet": "Yedioth Ahronoth", "political_leaning": "center",
        "country": "Israel"},
    3: {"outlet": "Kayhan", "political_leaning": "right", "country": "Iran"},
}

# The real list is div.results; the skeleton is div.results[aria-hidden=true].
OLD_RESULTS = 'div.results:not([aria-hidden="true"])'
SKELETON = 'div.results[aria-hidden="true"]'

# Playwright's locator and assertion APIs block until a pending navigation
# finishes, which is precisely the window under test — they would report on the
# page that loads afterwards. page.evaluate() runs against the live document
# instead, so the whole loading state is captured in one atomic call and
# asserted in Python.
PROBE = """() => {
  const skeleton = document.querySelector('div.results[aria-hidden="true"]');
  const previous = document.querySelector('div.results:not([aria-hidden="true"])');
  const more = document.querySelector('.more');
  const status = document.querySelector('.loading-status');
  const row = document.querySelector('.skel-row');
  const mainEl = document.querySelector('main');
  return {
    skeletonPresent: !!skeleton,
    skeletonRows: document.querySelectorAll('.skel-row').length,
    previousDisplay: previous ? getComputedStyle(previous).display : null,
    moreDisplay: more ? getComputedStyle(more).display : null,
    ariaBusy: mainEl ? mainEl.getAttribute('aria-busy') : null,
    statusText: status ? status.textContent.trim() : null,
    statusHeight: status ? status.getBoundingClientRect().height : null,
    rowTop: row ? row.getBoundingClientRect().top : null,
    viewportHeight: window.innerHeight,
  };
}"""


def build_article(index: int) -> Articles:
    """
    Builds an in-memory article so the tests never touch Postgres.

    :param index: the article's position, used to vary its content
    :return: an unsaved article
    """

    article = Articles()
    article.id = index
    article.source_id = (index % 3) + 1
    article.headline = f"כותרת {index}"
    article.translated_headline = f"Headline number {index}"
    article.link = f"https://www.example{index}.com/article"
    article.summary = f"Summary for article number {index}."
    article.references_original = ["מקור"]
    article.references_translated = ["A quoted line from the article"]
    article.tags = ["Strait of Hormuz", "Shipping"]
    article.captured_at = datetime(2026, 6, 20, 18, 0, tzinfo=timezone.utc)
    return article


ARTICLES = [build_article(i) for i in range(1, 10)]


class StubSearchService:
    """Stands in for SearchService, optionally sleeping so the skeleton lasts."""

    delay = 0.0

    def hybrid_search(self, text: str) -> list[tuple[int, Articles]]:
        if StubSearchService.delay:
            time.sleep(StubSearchService.delay)
        return list(enumerate(ARTICLES, start=1))


class SearchLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.get_search_service = lambda: StubSearchService()
        main.get_sources_by_ids = lambda ids: {
            key: value for key, value in SOURCES.items() if key in set(ids)
        }
        main.app.logger.disabled = True

        # threaded=True is required: the browser has to fetch search.js and
        # osipress.css while a search request is sleeping.
        cls.server = make_server(HOST, PORT, main.app, threaded=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.thread.join(timeout=5)

    def setUp(self):
        StubSearchService.delay = 0.0

    def open_page(self, viewport):
        page = self.browser.new_page(viewport=viewport)
        self.addCleanup(page.close)
        return page

    def slow_search(self):
        """Makes the next search block, so its loading state is observable."""

        StubSearchService.delay = SEARCH_DELAY
        self.addCleanup(setattr, StubSearchService, "delay", 0.0)

    def capture_loading_state(self, page):
        """
        Polls the live document until the skeleton has been inserted.

        :param page: the page mid-search
        :return: a snapshot of the loading state
        """

        state = {}
        for _ in range(40):
            state = page.evaluate(PROBE)
            if state["skeletonPresent"]:
                return state
            page.wait_for_timeout(25)
        return state

    def assert_loading(self, state, query=None):
        self.assertTrue(state["skeletonPresent"], "skeleton was never inserted")
        self.assertEqual(3, state["skeletonRows"])
        self.assertEqual("true", state["ariaBusy"])

        # The regression this suite exists for: `hidden` alone did not conceal
        # .results/.more, because a user-agent rule loses to an author
        # `display` declaration, so the old results stayed on top.
        self.assertIn(state["previousDisplay"], (None, "none"),
                      "previous results still visible behind the skeleton")
        self.assertIn(state["moreDisplay"], (None, "none"),
                      "'Show more' still visible behind the skeleton")

        self.assertIsNotNone(state["statusText"])
        self.assertGreater(state["statusHeight"], 0)
        if query:
            self.assertIn(query, state["statusText"])

        # Being in the DOM is not enough — under the bug the skeleton was
        # rendered below the old results, off the bottom of the screen.
        self.assertIsNotNone(state["rowTop"], "skeleton row has no layout box")
        self.assertGreaterEqual(state["rowTop"], 0)
        self.assertLess(state["rowTop"], state["viewportHeight"],
                        "skeleton rendered below the fold")

    def submit_query(self, page, query):
        page.fill("#q", query)
        page.click(".searchbar button")

    # ---- cases -----------------------------------------------------------

    def test_skeleton_shows_when_searching_from_empty_state(self):
        for viewport in (DESKTOP, MOBILE):
            with self.subTest(viewport=viewport["width"]):
                page = self.open_page(viewport)
                page.goto(f"{BASE}/search")

                self.slow_search()
                self.submit_query(page, "hormuz")
                self.assert_loading(self.capture_loading_state(page), "hormuz")

    def test_skeleton_shows_when_searching_again_from_results(self):
        """The reported bug: worked once, then never again on the same page."""

        for viewport in (DESKTOP, MOBILE):
            with self.subTest(viewport=viewport["width"]):
                page = self.open_page(viewport)
                page.goto(f"{BASE}/search?q=hormuz")
                expect(page.locator(f"{OLD_RESULTS} .story").first).to_be_visible()

                self.slow_search()
                self.submit_query(page, "lebanon")
                self.assert_loading(self.capture_loading_state(page), "lebanon")

    def test_skeleton_shows_when_clicking_a_topic_pill(self):
        page = self.open_page(DESKTOP)
        page.goto(f"{BASE}/search?q=hormuz")

        self.slow_search()
        page.locator("a.topic").first.click()
        self.assert_loading(self.capture_loading_state(page), "Strait of Hormuz")

    def test_skeleton_shows_when_clicking_show_more(self):
        page = self.open_page(DESKTOP)
        page.goto(f"{BASE}/search?q=hormuz")

        self.slow_search()
        page.locator(".more a").first.click()
        self.assert_loading(self.capture_loading_state(page), "hormuz")

    def test_skeleton_repaints_rather_than_only_mutating_the_dom(self):
        """
        Guards the earlier regression where the skeleton was inserted but the
        browser never painted it, because submitting a form starts tearing the
        document down. Secondary to the assertions above: taking a screenshot
        itself forces a render.
        """

        page = self.open_page(DESKTOP)
        page.goto(f"{BASE}/search?q=hormuz")
        expect(page.locator(f"{OLD_RESULTS} .story").first).to_be_visible()

        before = page.screenshot()
        self.slow_search()
        self.submit_query(page, "lebanon")
        self.assert_loading(self.capture_loading_state(page))
        during = page.screenshot()

        self.assertNotEqual(
            before, during,
            "page looks unchanged while searching, so nothing was repainted"
        )

    def test_back_button_restores_results_rather_than_a_frozen_skeleton(self):
        page = self.open_page(DESKTOP)
        page.goto(f"{BASE}/search?q=hormuz")

        self.slow_search()
        self.submit_query(page, "lebanon")
        self.assert_loading(self.capture_loading_state(page), "lebanon")

        page.wait_for_url("**/search?q=lebanon", timeout=15_000)
        expect(page.locator(f"{OLD_RESULTS} .story").first).to_be_visible()

        page.go_back()
        page.wait_for_url("**/search?q=hormuz", timeout=15_000)
        expect(page.locator(f"{OLD_RESULTS} .story").first).to_be_visible()
        expect(page.locator(SKELETON)).to_have_count(0)
        expect(page.locator("main")).not_to_have_attribute("aria-busy", "true")

    def test_nav_search_link_does_not_trigger_loading(self):
        """The nav link carries no query, so it should navigate normally."""

        page = self.open_page(DESKTOP)
        page.goto(f"{BASE}/search?q=hormuz")
        page.locator('.navlinks a[href="/search"]').click()

        page.wait_for_url("**/search", timeout=15_000)
        expect(page.locator(SKELETON)).to_have_count(0)
        expect(page.locator("main")).not_to_have_attribute("aria-busy", "true")


if __name__ == "__main__":
    unittest.main()
