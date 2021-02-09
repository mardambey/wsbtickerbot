FROM python:latest

RUN pip install praw yfinance pandas_datareader vaderSentiment cache_to_disk tweepy

