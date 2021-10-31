from ServerQueue import ServerQueue
from Song import Song
import requests
import re



def get_song(query: str, sq: ServerQueue):
    if query.count("youtube.com"):
        song = Song(url=query)
    elif query.count("open.spotify.com/track"):
        raw_html = requests.get(query).text
        songname = re.findall("<title>.+</title>", raw_html)[0].replace("<title>", "").replace(" | Spotify</title>", "")
        url = "https://www.youtube.com/results?"
        params = {"search_query": songname}
        raw_html = requests.get(url=url, params=params).text
        song = Song(url=f"https://www.youtube.com/watch?v=" + re.findall(r'/watch\?v=(.{11})', raw_html)[0])
    else:
        url = "https://www.youtube.com/results?"
        params = {"search_query": query}
        raw_html = requests.get(url=url, params=params).text
        song = Song(url=f"https://www.youtube.com/watch?v="+re.findall(r'/watch\?v=(.{11})', raw_html)[0])

    sq.queue.append(song)
    return song