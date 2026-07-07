
import json

import feedparser
import requests


with open("sources.json", "r") as file:
    data = json.load(file)

for country, sources in data.items():

    # iterate through major sources per country
    for source in sources:
        print(data[country][source])
        url = data[country][source]["url"]
        feed = feedparser.parse(url)
        print("Feed title: " + feed.feed.title)