import asyncio
import youtube_dl
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
    def __init__(self, *, url=None):
        self.url = url

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
            title_formatted = self.title + " "*(38-len(self.title))
        else:
            title_formatted = self.title[:35]+"..."
        self.queue_string = f"{title_formatted} {self.length_formatted}"