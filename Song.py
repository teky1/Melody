import asyncio
import youtube_dl
import requests
import re
from urllib.error import HTTPError

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [
        {
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }
    ],
}

class Song:
    def __init__(self, *, url=None, lazy_loaded=False, query=None, added_by=None):
        self.url = url
        self.query = query

        self.loaded = False
        self.info_dict = None
        self.title = None
        self.length = None
        self.length_formatted = None
        self.title_formatted = None
        self.queue_string = None


        if not lazy_loaded:
            if self.url is None:
                self.get_yt_url()
            self.load()

    def ensure_loaded(self):
        if self.url is None:
            self.get_yt_url()
        if not self.loaded:
            self.load()

    def get_yt_url(self):
        url = "https://www.youtube.com/results?"
        params = {"search_query": self.query}
        raw_html = requests.get(url=url, params=params).text
        self.url = f"https://www.youtube.com/watch?v=" + re.findall(r'/watch\?v=(.{11})', raw_html)[0]


    def load(self):
        request_success = False

        retries = 0
        while not request_success and retries < 5:
            try:
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(self.url, download=False)
                request_success = True
            except HTTPError:
                retries += 1
                for x in range(10):
                    print("YOU WERE RIGHT ABOUT THE HTTP FORBIDDEN 403 ERROR THING")

        self.info_dict = info_dict
        self.title = self.info_dict.get("title", "No Title Found")
        self.length = self.info_dict.get("duration", 0)
        self.length_formatted = f"{round(self.length / 60)}:{str(self.length % 60).zfill(2)}"
        if self.length_formatted == "0:0.0":
            self.length_formatted = "∞:∞"
            self.length = 60

        if len(self.title) <= 38:
            self.title_formatted = self.title + " " * (38 - len(self.title))
        else:
            self.title_formatted = self.title[:35] + "..."
        self.queue_string = f"{self.title_formatted} {self.length_formatted}"
        self.loaded = True