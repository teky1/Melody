from ServerQueue import ServerQueue
from Song import Song

import requests
import re
import json
import threading
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from discord.ext import commands

with open("secrets.json") as secret_file:
    secrets = json.load(secret_file)

auth_manager = SpotifyClientCredentials(client_id=secrets["spotify_client_id"],
                                        client_secret=secrets["spotify_client_secret"])
sp = spotipy.Spotify(auth_manager=auth_manager)

async def get_songs_from_spotify_playlist(playlist_id):
    pl = sp.playlist_items(playlist_id, market="US")
    tracks = pl["items"]
    while pl["next"]:
        pl = sp.next(pl)
        tracks.extend(pl["items"])
    track_names = []
    for track in tracks:
        name = track["track"]["name"]
        artists = [artist["name"] for artist in track["track"]["artists"]]
        track_names.append(f"{name} - {', '.join(artists)}")
    return track_names

def get_yt_link_from_name(name, return_obj=None, index=0):
    url = "https://www.youtube.com/results?"
    params = {"search_query": name}
    raw_html = requests.get(url=url, params=params).text
    try:
        song = Song(url=f"https://www.youtube.com/watch?v=" + re.findall(r'/watch\?v=(.{11})', raw_html)[0])
    except IndexError:
        song = False
    if return_obj is None:
        return song
    else:
        return_obj[index] = song

def run_list_of_songs(songlist, return_obj):
    for i,song in enumerate(songlist):
        get_yt_link_from_name(song, return_obj, i)

def split(a, n):
    k, m = divmod(len(a), n)
    return (a[i*k+min(i, m):(i+1)*k+min(i+1, m)] for i in range(n))

async def get_song(query: str, sq: ServerQueue, ctx: commands.Context):

    is_playlist = False
    song = False
    if query.count("youtube.com") and query.count("&list=") < 1:
        song = Song(url=query)
        sq.queue.append(song)
    elif query.count("open.spotify.com/track"):
        raw_html = requests.get(query).text
        songname = re.findall("<title>.+</title>", raw_html)[0].replace("<title>", "").replace(" | Spotify</title>", "")

        song = get_yt_link_from_name(songname)
        if song == False:
            await ctx.send(f"Couldn't find YouTube video for `{songname}`")
        else:
            sq.queue.append(song)
    elif query.count("open.spotify.com/playlist"):
        is_playlist = True
        playlist_id = query.split("/")[-1].split("?")[0]

        songs = await get_songs_from_spotify_playlist(playlist_id)
        song_count = len(songs)


        for song in songs:
            sq.queue.append(Song(lazy_loaded=True, query=song))
        song = song_count


    else:
        song = get_yt_link_from_name(query)
        if song == False:
            await ctx.send(f"Couldn't find YouTube video for `{query}`")
        else:
            sq.queue.append(song)

    return song, is_playlist
