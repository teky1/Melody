import youtube_dl

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

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(self.url, download=False)

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