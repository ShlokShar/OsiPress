
import json

import feedparser
import requests

from cron.util.ai_service import AIService
from cron.util.article import get_article_text
from cron.util.translation import translate

MAX_ARTICLES = 3

ai_service = AIService()
with open("sources.json", "r") as file:
    data = json.load(file)

for country, sources in data.items():
    press_information = {} # will contain 3 sources with MAX_ARTICLES objects
    # each.

    # iterate through major sources per country
    for source in sources:
        press_information[source] = {} # set the source

        url = data[country][source]["url"]
        feed = feedparser.parse(url) # parse the RSS

        # go through each object in the RSS
        for entry in feed.entries:
            # end iteration once there are enough articles recorded for this
            # source
            if len(press_information[source]) >= MAX_ARTICLES:
                break

            headline = entry.title
            relevant = ai_service.classify(headline)
            link = entry.link

            # if this headline is not political at all, then skip
            if not relevant:
                continue

            # get the article text and summarize it
            translated_headline = translate(headline)
            article_text = get_article_text(link)
            processed_article = ai_service.summarize(article_text)

            # save the summary and references
            article_summary = processed_article.summary if processed_article \
                else "No summary provided."
            article_references = processed_article.references \
                if processed_article else ["No references provided."]

            press_information[source][headline] = {article_summary: article_references}

    print(press_information)