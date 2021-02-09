#!/usr/bin/env python

import datetime
import json
import operator
import pandas as pd
import pprint
import praw
import re
import sys
import time
import yfinance as yf
import tweepy

from tweepy import OAuthHandler
from cache_to_disk import cache_to_disk
from datetime import date
from functools import cache
from pandas_datareader import data as pdr
from praw.models import MoreComments
from urllib.request import Request, urlopen
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

yf.pdr_override()

@cache_to_disk(90)
def ticker_data(ticker):
    #print("Downloading data for ticker %s\n" %(ticker))
    lastBusDay = datetime.datetime.today()
    shift = datetime.timedelta(max(1,(lastBusDay.weekday() + 6) % 7 - 3))
    lastBusDay = lastBusDay - shift
    return pdr.get_data_yahoo(ticker, lastBusDay.strftime('%Y-%m-%d'))

def extract_ticker(body, start_index):
   """
   Given a starting index and text, this will extract the ticker, return None if it is incorrectly formatted.
   """
   count  = 0
   ticker = ""

   for char in body[start_index:]:
      # if it should return
      if not char.isalpha():
         # if there aren't any letters following the $
         if (count == 0):
            return None

         return ticker.upper()
      else:
         ticker += char
         count += 1

   return ticker.upper()

def find_tickers(ticker_dict, text):
   """ Parses the text of each comment/reply """
   blacklist_words = [
      "YOLO", "TOS", "CEO", "CFO", "CTO", "DD", "BTFD", "WSB", "OK", "RH",
      "KYS", "FD", "TYS", "US", "USA", "IT", "ATH", "RIP", "BMW", "GDP",
      "OTM", "ATM", "ITM", "IMO", "LOL", "DOJ", "BE", "PR", "PC", "ICE",
      "TYS", "ISIS", "PRAY", "PT", "FBI", "SEC", "GOD", "NOT", "POS", "COD",
      "AYYMD", "FOMO", "TL;DR", "EDIT", "STILL", "LGMA", "WTF", "RAW", "PM",
      "LMAO", "LMFAO", "ROFL", "EZ", "RED", "BEZOS", "TICK", "IS", "DOW"
      "AM", "PM", "LPT", "GOAT", "FL", "CA", "IL", "PDFUA", "MACD", "HQ",
      "OP", "DJIA", "PS", "AH", "TL", "DR", "JAN", "FEB", "JUL", "AUG",
      "SEP", "SEPT", "OCT", "NOV", "DEC", "FDA", "IV", "ER", "IPO", "RISE"
      "IPA", "URL", "MILF", "BUT", "SSN", "FIFA", "USD", "CPU", "AT",
      "GG", "ELON", "HOLD", "A", "E", "EV", "AM", "U", "AND", "D", "MOON"
   ]

   def check_and_add_ticker(ticker):
       data = ticker_data(word)
       if len(data.Close) > 0:
           price = data.Close[-1]
           if word in ticker_dict:
               ticker_dict[word].count += 1
               ticker_dict[word].bodies.append(text)
           else:
               ticker_dict[word] = Ticker(word)
               ticker_dict[word].count = 1
               ticker_dict[word].bodies.append(text)

   # $TICKER format
   if '$' in text:
      index = text.find('$') + 1
      word = extract_ticker(text, index)
      
      if word and word not in blacklist_words:
         try:
            check_and_add_ticker(word)
         except Exception as e:
            #print(e)
            pass
   
   # TICKER format
   word_list = re.sub("[^\w]", " ",  text).split()
   for count, word in enumerate(word_list):
      # initial screening of words to check if they are a ticker
      # and len(word) != 1 # skip 1 letter words
      if word.isupper() and (word.upper() not in blacklist_words) and len(word) <= 5 and word.isalpha():
         try:
            check_and_add_ticker(word)
         except Exception as e:
            #print(e)
            continue 

   return ticker_dict

def get_url(key, value, total_count):
   # determine whether to use plural or singular
   mention = ("mentions", "mention") [value == 1]
   if int(value / total_count * 100) == 0:
         perc_mentions = "<1"
   else:
         perc_mentions = int(value / total_count * 100)
   #return "{0} | [{1} {2} ({3}%)](https://finance.yahoo.com/quote/{0}?p={0})".format(key, value, mention, perc_mentions)
   return "{0} | [{1} {2} ({3}%)](https://marketchameleon.com/Overview/{0}/OptionChain/?ac=volume)".format(key, value, mention, perc_mentions)

def get_date():
   now = datetime.datetime.now()
   return now.strftime("%b %d, %Y")

class TwitterSource:
    def __init__(self, ticker):
        self.ticker = ticker

    def load(self, ticker_dict, max_tweets):
        with open("config.json") as json_data_file:
           data = json.load(json_data_file)
     
        auth = tweepy.OAuthHandler(data["twitter"]["consumer_key"], data["twitter"]["consumer_secret"])
        auth.set_access_token(data["twitter"]["access_token"], data["twitter"]["access_token_secret"])
        user = tweepy.API(auth)
        tweets = tweepy.Cursor(user.search, q=str(self.ticker), tweet_mode='extended', lang='en').items(max_tweets)
        for tweet in tweets:
            tw = tweet.full_text
            ticker_dict = find_tickers(ticker_dict, tw)

class RedditSource:
    def __init__(self, sub = "wallstreetbets"):
        self.sub = sub

    def load(self, ticker_dict, num_submissions):
        subreddit = self.setup()
        new_posts = subreddit.new(limit=num_submissions)

        for count, post in enumerate(new_posts):
            # if we have not already viewed this post thread
            if not post.clicked:
                # parse the post's title's text
               ticker_dict = find_tickers(ticker_dict, post.title)

               # search through all comments and replies to comments
               comments = post.comments
               for comment in comments:
                   # without this, would throw AttributeError since the instance in this represents the "load more comments" option
                  if isinstance(comment, MoreComments):
                      continue
                  ticker_dict = find_tickers(ticker_dict, comment.body)

                  # iterate through the comment's replies
                  replies = comment.replies
                  for rep in replies:
                      # without this, would throw AttributeError since the instance in this represents the "load more comments" option
                     if isinstance(rep, MoreComments):
                         continue
                     ticker_dict = find_tickers(ticker_dict, rep.body)

               # update the progress count
               #print("{0} / {1} {2}".format(count + 1, num_submissions, post.title))
               #sys.stdout.write("\rProgress: {0} / {1} posts: {2}".format(count + 1, num_submissions, post.title))
               #sys.stdout.flush()

    def setup(self):
        with open("config.json") as json_data_file:
           data = json.load(json_data_file)
     
        # create a reddit instance
        reddit = praw.Reddit(client_id=data["reddit"]["client_id"], client_secret=data["reddit"]["client_secret"],
                             username=data["reddit"]["username"], password=data["reddit"]["password"],
                             user_agent=data["reddit"]["user_agent"])
        # create an instance of the subreddit
        subreddit = reddit.subreddit(self.sub)
        return subreddit

def run(mode, num_submissions):
   ticker_dict = {}
   text = ""
   total_count = 0

   # find tickers on Reddit and analyze their posts
   r = RedditSource()
   r.load(ticker_dict, num_submissions)

   # analyze those same tickers on Twitter, but add a $ infront to improve the search results
   for key in list(ticker_dict):
      t = TwitterSource("$%s" % (key))
      t.load(ticker_dict, num_submissions)

   text += "\n\nTicker | Mentions | Bullish (%) | Neutral (%) | Bearish (%)\n"

   print("Tickers found: %s" % (ticker_dict.keys()))
   total_mentions = 0
   ticker_list = []
   for key in ticker_dict:
      # print(key, ticker_dict[key].count)
      total_mentions += ticker_dict[key].count
      ticker_list.append(ticker_dict[key])

   ticker_list = sorted(ticker_list, key=operator.attrgetter("count"), reverse=True)

   for ticker in ticker_list:
      Ticker.analyze_sentiment(ticker)

   # will break as soon as it hits a ticker with fewer than 5 mentions
   for count, ticker in enumerate(ticker_list):
      if count == 25:
         break
      
      url = get_url(ticker.ticker, ticker.count, total_mentions)
      # setting up formatting for table
      text += "\n{} | {} | {} | {}".format(url, ticker.bullish, ticker.bearish, ticker.neutral)

   print(text)

class Ticker:
   def __init__(self, ticker):
      self.ticker = ticker
      self.count = 0
      self.bodies = []
      self.pos_count = 0
      self.neg_count = 0
      self.bullish = 0
      self.bearish = 0
      self.neutral = 0
      self.sentiment = 0 # 0 is neutral

   def analyze_sentiment(self):
      analyzer = SentimentIntensityAnalyzer()
      neutral_count = 0
      for text in self.bodies:
         sentiment = analyzer.polarity_scores(text)
         if (sentiment["compound"] > .005) or (sentiment["pos"] > abs(sentiment["neg"])):
            self.pos_count += 1
         elif (sentiment["compound"] < -.005) or (abs(sentiment["neg"]) > sentiment["pos"]):
            self.neg_count += 1
         else:
            neutral_count += 1

      self.bullish = int(self.pos_count / len(self.bodies) * 100)
      self.bearish = int(self.neg_count / len(self.bodies) * 100)
      self.neutral = int(neutral_count / len(self.bodies) * 100)

if __name__ == "__main__":
   # USAGE: wsbtickerbot.py [ num_submissions ]
   mode = 0
   num_submissions = 500

   if len(sys.argv) > 1:
      mode = 1
      num_submissions = int(sys.argv[1])

   run(mode, num_submissions)

