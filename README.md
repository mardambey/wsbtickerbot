# wsbtickerbot

wsbtickerbot is a Reddit bot, developed utilizing the Reddit PRAW API, that scrapes the entirety of r/wallstreetbets over a 24 hour period, collects all the tickers mentioned, and then performs sentiment analysis on the context. The sentiment analysis is used to classify the stocks into three categories: bullish, neutral, and bearish.

# Docker

Building:

    docker build -f Dockerfile -t mardambey/wsbtickerbot .


Running:

    docker run --rm -it -v $(pwd):/app mardambey/wsbtickerbot bash
    cd /app
    python wsbtickerbot.py test 500


