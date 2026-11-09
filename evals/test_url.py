import unittest

from cron.util.url import normalize_article_url


class ArticleURLNormalizationTests(unittest.TestCase):
    def test_removes_tracking_and_fragment(self):
        self.assertEqual(
            normalize_article_url(
                "HTTPS://Example.COM/story/?id=7&utm_source=rss&"
                "fbclid=abc#section"
            ),
            "https://example.com/story?id=7",
        )

    def test_preserves_meaningful_query_order(self):
        self.assertEqual(
            normalize_article_url(
                "https://example.com/story?edition=he&page=2"
            ),
            "https://example.com/story?edition=he&page=2",
        )

    def test_removes_default_port(self):
        self.assertEqual(
            normalize_article_url("https://EXAMPLE.com:443/story/"),
            "https://example.com/story",
        )

    def test_rejects_invalid_urls(self):
        invalid_urls = [
            "",
            "example.com/story",
            "file:///tmp/story",
            "https://user@x.com/a",
        ]
        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_article_url(url)


if __name__ == "__main__":
    unittest.main()
