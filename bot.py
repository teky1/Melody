import json
import math
import re
import threading

import discord
import random

import requests
from discord.ext import commands
from discord.ext.commands import BucketType
from discord.utils import get
from discord import FFmpegPCMAudio
from ServerQueue import ServerQueue
from song_grabber import get_song
from Song import Song
import database_manager as db
import typing
import spotipy
import ytmusicapi

client = commands.Bot(command_prefix="-", intents=discord.Intents.all())
server_queues = {}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}



@client.event
async def on_ready():
    print("Ready.")

# is in vc check
def is_in_our_vc():
    async def predicate(ctx: commands.Context):
        if ctx.message.author.voice is None:
            await ctx.send("You need to be in a VC to use this command")
            return False
        if ctx.voice_client is None:
            return True
        if ctx.message.author.voice.channel == ctx.voice_client.channel:
            return True
        else:
            await ctx.send("You need to be in the bot's VC to use this command.")
            return False
    return commands.check(predicate)

def ensure_queue():
    async def predicate(ctx:commands.Context):
        if ctx.guild.id not in server_queues:
            server_queues[ctx.guild.id] = ServerQueue(ctx.guild)
        return True
    return commands.check(predicate)

def ensure_spotify_linked():
    async def predicate(ctx: commands.Context):
        if db.getSpotifyKey(ctx.author.id) is None:
            await ctx.send("You need to have Spotify linked to use this command. You can link your account"
                           "by using the `-spotify` command.")
            return False
        return True
    return commands.check(predicate)

@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if client.user.id == member.id and before.channel is not None and after.channel is None:
        sq = server_queues[before.channel.guild.id]
        sq.is_playing = False
        sq.current_queue_number = None
        sq.looping = False
        sq.queue.clear()
        try:
            await sq.server.voice_client.disconnect(force=True)
        except AttributeError:
            pass
        sq.channel = None
        await sq.active_text_channel.send("Leaving VC and clearing queue...")


def play_song(sq, channel):
    sq.is_playing = True
    voice = get(client.voice_clients, channel=channel)
    sq.current_song().ensure_loaded()
    voice.play(FFmpegPCMAudio(sq.current_song().info_dict["url"], **FFMPEG_OPTIONS),
               after=lambda x: on_song_end(sq, channel))


def on_song_end(sq, channel):
    if sq.current_queue_number is None:
        return
    elif sq.current_queue_number < len(sq.queue) - 1:
        sq.current_queue_number += 1
    elif not sq.looping and sq.current_queue_number == len(sq.queue) - 1:
        sq.is_playing = False
        return
    elif sq.looping and sq.current_queue_number == len(sq.queue) - 1:
        sq.current_queue_number = 0

    play_song(sq, channel)

@is_in_our_vc()
@ensure_queue()
@client.command(name="play", aliases=["p"])
async def play(ctx: commands.Context, *, query: str):
    sq = server_queues[ctx.guild.id]
    sq.active_text_channel = ctx.channel
    channel = ctx.author.voice.channel

    current_queue_length = len(sq.queue)

    song, is_playlist = await get_song(query, sq, ctx)

    if song is False:
        await ctx.send("There was an error trying to retrieve the song.")

    if sq.channel != channel:
        print("here1")
        await channel.connect()
        print("here2")
        sq.channel = channel



    if not is_playlist:
        await ctx.send(f"Added `{song.title}` ({song.length_formatted})")
    else:
        await ctx.send(f"Added `{song}` songs.")

    if not sq.is_playing:
        sq.current_queue_number = current_queue_length
        play_song(sq, channel)

@is_in_our_vc()
@ensure_queue()
@client.command(name="music", aliases=["m"])
async def music(ctx: commands.Context, *, query: str):
    sq = server_queues[ctx.guild.id]
    sq.active_text_channel = ctx.channel
    channel = ctx.author.voice.channel

    current_queue_length = len(sq.queue)

    song, is_playlist = await get_song(query, sq, ctx, True)

    if song is False:
        await ctx.send("There was an error trying to retrieve the song.")

    if sq.channel != channel:
        await channel.connect()
        sq.channel = channel

    if not is_playlist:
        await ctx.send(f"Added `{song.title}` ({song.length_formatted})")
    else:
        await ctx.send(f"Added `{song}` songs.")

    if not sq.is_playing:
        sq.current_queue_number = current_queue_length
        play_song(sq, channel)


@is_in_our_vc()
@client.command(name="disconnect", aliases=["dc", "die", "leave"])
async def disconnect(ctx: commands.Context):
    try:
        sq = server_queues[ctx.guild.id]
        sq.active_text_channel = ctx.channel
    except KeyError:
        pass
    await ctx.voice_client.disconnect()


@is_in_our_vc()
@ensure_queue()
@client.command(name="clear")
async def clear(ctx: commands.Context):
    sq = server_queues[ctx.guild.id]
    sq.is_playing = False
    sq.current_queue_number = None
    sq.looping = False
    sq.queue.clear()
    ctx.voice_client.stop()
    await ctx.send(":broom: Cleared the queue")

@ensure_queue()
@client.command(name="queue", aliases=["q"])
async def queue(ctx: commands.Context, page: typing.Optional[int] = None):
    message = "```\n"
    sq = server_queues[ctx.guild.id]
    total_length = len(sq.queue)

    if total_length == 0:
        await ctx.send("```The queue is empty :(```")
        return

    total_pages = int(math.ceil(total_length/10))

    page = int(math.ceil((sq.current_queue_number+1)/10)) if page is None else page
    message += f"Queue - Page {page} of {total_pages}\n\n"

    if page > total_pages or page < 1:
        await ctx.send("Invalid page number.")
        return

    queue_page = sq.queue[(page-1)*10:(page-1)*10+10]

    async with ctx.typing():
        threads = []
        for i,song in enumerate(queue_page):
            threads.append(threading.Thread(target=song.ensure_loaded))
            threads[i].start()

        for thread in threads:
            thread.join()

        for i, song in enumerate(queue_page):
            real_index = (page-1)*10+i
            prefix = " >>> " if sq.current_queue_number == real_index else "     "
            message += f"{prefix} {real_index+1}) {sq.queue[real_index].queue_string}\n"

        message += "\n🔁 Looping queue" if sq.looping else "\nNot Looping"

        message += f"\n-queue <page>" \
                   "```"
    await ctx.send(message[:1950])

@is_in_our_vc()
@client.command(name="skip", aliases=["next", "nextsong", "s"])
async def skip(ctx: commands.Context, amount: typing.Optional[int] = 1):
    vc = ctx.author.voice.channel
    sq = server_queues[ctx.guild.id]
    sq.active_text_channel = ctx.channel
    curr_queue_num = sq.current_queue_number if sq.current_queue_number is not None else 0
    if curr_queue_num + amount >= len(sq.queue) or curr_queue_num + amount < 0:
        await ctx.send("There's no song to skip to there.")
        return
    playing_song = sq.queue[curr_queue_num + amount]
    playing_song.ensure_loaded()
    await ctx.send(f"Now Playing: `{playing_song.title}` ({playing_song.length_formatted})")
    ctx.voice_client.stop()
    sq.current_queue_number = curr_queue_num + amount
    play_song(sq, channel=sq.channel)
    sq.current_queue_number -= 1


@is_in_our_vc()
@client.command(name="jump", aliases=["jumpto", "skipto", "j"])
async def jump(ctx: commands.Context, queue_num: int):
    vc = ctx.author.voice.channel
    sq = server_queues[ctx.guild.id]
    sq.active_text_channel = ctx.channel
    queue_num -= 1
    if queue_num < 0 or queue_num >= len(sq.queue):
        await ctx.send("There is no song there.")
        return
    playing_song = sq.queue[queue_num]
    playing_song.ensure_loaded()
    await ctx.send(f"Now Playing: `{playing_song.title}` ({playing_song.length_formatted})")
    ctx.voice_client.stop()
    sq.current_queue_number = queue_num
    play_song(sq, sq.channel)
    sq.current_queue_number -= 1

@ensure_queue()
@client.command(name="info", aliases=["url", "link", "i"])
async def info(ctx: commands.Context, queue_num: int):
    sq = server_queues[ctx.guild.id]
    if queue_num < 1 or queue_num > len(sq.queue):
        await ctx.send(f"There is no Song #{queue_num}")
        return
    song = sq.queue[queue_num-1]
    song.ensure_loaded()
    await ctx.send(f"Song #{queue_num}: `{song.title}`\n({song.url})")

@is_in_our_vc()
@ensure_queue()
@client.command(name="remove", aliases=["delete", "rm"])
async def remove(ctx: commands.Context, id: int):
    sq = server_queues[ctx.guild.id]
    if id < 1 or id > len(sq.queue):
        await ctx.send("There is no song there")
        return
    elif id - 1 > sq.current_queue_number:
        removed = sq.queue.pop(id - 1)
    elif id - 1 < sq.current_queue_number:
        removed = sq.queue.pop(id - 1)
        sq.current_queue_number -= 1
    elif id - 1 == sq.current_queue_number:
        ctx.voice_client.stop()
        sq.current_queue_number = sq.current_queue_number + 1
        play_song(sq, channel=sq.channel)
        sq.current_queue_number -= 2
        removed = sq.queue.pop(id - 1)
    else:
        await ctx.send("an error ocurred dm teky")
        return

    removed.ensure_loaded()

    await ctx.send(f"Removed `{removed.title}`")


@is_in_our_vc()
@client.command(name="shuffle", aliases=["randomize",])
async def shuffle(ctx: commands.Context):
    sq = server_queues[ctx.guild.id]
    if sq.is_playing:
        current_song = sq.current_song()
        current_queue_position = sq.current_queue_number

        random.shuffle(sq.queue)

        new_index = sq.queue.index(current_song)
        sq.queue[new_index], sq.queue[current_queue_position] = sq.queue[current_queue_position], sq.queue[new_index]
    else:
        random.shuffle(sq.queue)

    await ctx.send(":twisted_rightwards_arrows: **Shuffled Queue!** *(-queue to see new updated queue)*")


@is_in_our_vc()
@ensure_queue()
@client.command(name="loop")
async def loop(ctx: commands.Context):
    sq = server_queues[ctx.guild.id]
    sq.active_text_channel = ctx.channel
    if sq.looping:
        await ctx.send(":repeat_one: No longer looping queue!")
        sq.looping = False
    else:
        await ctx.send(":repeat: Now looping queue!")
        sq.looping = True

@ensure_queue()
@client.command(name="nowplaying", aliases=["np"])
async def nowplaying(ctx: commands.Context):
    sq = server_queues[ctx.guild.id]
    song = sq.current_song()
    song.ensure_loaded()
    await ctx.send(f"Now Playing: `{song.title}`\n({song.url})")

@commands.is_owner()
@ensure_queue()
@client.command(name="status")
async def status(ctx: commands.Context):
    sq = server_queues[ctx.guild.id]
    await ctx.send(f"```\n"
                   f"Server: {sq.server}\n"
                   f"Is Playing: {sq.is_playing}\n"
                   f"Current Queue Num: {sq.current_queue_number}\n"
                   f"Queue: {str(sq.queue)[:1500]}\n"
                   f"VC: {sq.channel}\n"
                   f"Active Text Channel: {sq.active_text_channel}\n"
                   f"Looping: {sq.looping}\n"
                   f"```")

@client.command(name="search")
async def search(ctx: commands.Context, *, query: str):
    url = "https://www.youtube.com/results?"
    params = {"search_query": query}
    raw_html = requests.get(url=url, params=params).text
    urls = [f"https://www.youtube.com/watch?v=" + z for z in re.findall(r'/watch\?v=(.{11})', raw_html)][:5]

    threads = []
    songs = []
    async with ctx.typing():
        for vid in urls:
            song = Song(url=vid, lazy_loaded=True)
            songs.append(song)
            threads.append(threading.Thread(target=song.ensure_loaded))
            threads[-1].start()

        for thread in threads:
            thread.join()

        resp = "```--- Search Results ---\n"
        for i in range(len(songs)):
            resp += f"{i+1}) ({songs[i].length_formatted}) {songs[i].title[:75]}\n{songs[i].url}\n\n"
        resp += "To play one of these results, reply to this message with: -playresult <result #>```"

    await ctx.send(resp)

@is_in_our_vc()
@ensure_queue()
@client.command(name="playresult")
async def playresult(ctx: commands.Context, resultNum: typing.Optional[int] = None):
    if ctx.guild.id not in server_queues:
        server_queues[ctx.guild.id] = ServerQueue(ctx.guild)
    sq = server_queues[ctx.guild.id]
    sq.active_text_channel = ctx.channel
    try:
        referenced = await ctx.fetch_message(ctx.message.reference.message_id)
    except AttributeError:
        referenced = None

    if referenced is None or resultNum is None or not referenced.content.startswith("```--- Search Results ---\n"):
        await ctx.send("**Correct Usage:** This command is used to play a search result. First use `-search <query>` to "
                       "search for a query and then **REPLY** to the search results with the command `-playresult <result #>`"
                       "to play a specific one of the results.")
        return

    if resultNum > 5 or resultNum < 1:
        await ctx.send("Invalid Result Number")

    url = referenced.content.split("\n")[resultNum*3-1]
    await play(ctx, query=url)

@ensure_queue()
@client.command(name="saveplaylist", aliases=["savepl"])
async def saveplaylist(ctx: commands.Context, playlistName: typing.Optional[str]):
    sq = server_queues[ctx.guild.id]
    sq.active_text_channel = ctx.channel
    if playlistName is None:
        await ctx.send("**Correct Format**: -saveplaylist <playlist_name>")
        return
    if not playlistName.isalpha() or len(playlistName) > 30:
        await ctx.send("Playlist names must be alphabetic (no spaces or numbers) and under 30 letters long.")
        return
    if not db.getPlaylist(playlistName) is None:
        await ctx.send("A playlist with that name already exists.")
        return
    if len(sq.queue) < 1:
        await ctx.send("There are no songs in the queue to create a playlist with.")
        return

    tracks = []
    for song in sq.queue:
        if song.url is None:
            song.get_yt_url()
        tracks.append(song.url.split("?v=")[-1][:11])

    db.createPlaylist(playlistName, ctx.author.id, tracks)

    if db.getPlaylist(playlistName) is None:
        await ctx.send("There was an issue creating the playlist.")
    else:
        await ctx.send(f"Queue saved as playlist \"{playlistName}\"")

@ensure_queue()
@is_in_our_vc()
@commands.cooldown(rate=1, per=5, type=BucketType.member)
@client.command(name="playlist", aliases=["pl"])
async def playlist(ctx: commands.Context, playlistName: typing.Optional[str]):
    sq = server_queues[ctx.guild.id]
    sq.active_text_channel = ctx.channel
    channel = ctx.author.voice.channel

    if playlistName is None:
        await ctx.send("**Correct Format**: -playlist <playlist_name>")
        return

    playlist = db.getPlaylist(playlistName[:30])
    if playlist is None:
        await ctx.send(f"Playlist \"{playlistName}\" does not exist.")
        return
    playlist = playlist[-1].split(",")

    current_queue_length = len(sq.queue)

    for video_id in playlist:
        sq.queue.append(Song(url="https://www.youtube.com/watch?v="+video_id, lazy_loaded=True))

    if sq.channel != channel:
        await channel.connect()
        sq.channel = channel

    await ctx.send(f"Added `{len(playlist)}` songs")

    if not sq.is_playing:
        sq.current_queue_number = current_queue_length
        play_song(sq, channel)

@commands.cooldown(rate=1, per=5, type=BucketType.member)
@client.command(name="playlists", aliases=["listplaylists", "listpl"])
async def playlists(ctx: commands.Context):
    data = db.getAllData()
    # message = "**All Playlists**\n"
    embed = discord.Embed(title="All Playlists", color=0x595959)
    for pl in data:
        # message += f"{pl[0]} - {pl[2].count(',')+1} songs\n"
        embed.add_field(name=pl[0], value=f"{pl[2].count(',')+1} songs", inline=True)
    await ctx.send(embed=embed)

@commands.cooldown(rate=1, per=1, type=BucketType.member)
@client.command(name="spotify")
async def spotify(ctx: commands.Context):
    data_entry = db.getSpotifyKey(ctx.author.id)
    msg = ""
    if data_entry is None:
        msg += "🚫 No Spotify Account Linked"

        dm_message = "*How to link your Spotify account:*\n\n" \
                     f"1. Go to the following link and log in with Spotify: " \
                     f"https://joelchem.com/music/auth/{ctx.author.id} \n" \
                     f"2. **IMPORTANT:** Once you have logged in DM Teky#9703 the the email for " \
                     f"your Spotify account so he can add you to the whitelist. Your account will not be linked " \
                     f"until he adds you to the whitelist." \
                     f"\n\n*Once you're added to the whitelist you can run the `-spotify` command again" \
                     f"to make sure your account is properly linked*"
        await ctx.author.send(content=dm_message)

        msg += "\n\n*A DM has been sent to you with instructions on how to link your Spotify account.*"

    else:
        msg += "✅ Spotify Account Linked: "
        sp = spotipy.Spotify(auth=data_entry[1])
        try:
            msg += f'**{sp.current_user()["display_name"]}**'
        except spotipy.exceptions.SpotifyException:
            msg = "⚠ Account Not Whitelisted \n\n *You still need to DM Teky#9703 your Spotify email " \
                  "so he can add you to the whitelist. If you've already done this, it may take a few minutes " \
                  "for the whitelist to update so try again in a bit.*"

    await ctx.send(msg)

@ensure_queue()
@is_in_our_vc()
@commands.cooldown(rate=1, per=1, type=BucketType.member)
@client.command(name="recent", aliases=["recenttop","toprecent"])
async def recent(ctx: commands.Context, target: typing.Optional[discord.Member] = None):
    sq = server_queues[ctx.guild.id]
    sq.active_text_channel = ctx.channel
    channel = ctx.author.voice.channel
    current_queue_length = len(sq.queue)

    id = ctx.author.id if target is None else target.id
    key = db.getSpotifyKey(id)

    if key is None and target is None:
        await ctx.send("You need to have Spotify linked to use this command. You can link your account"
                       "by using the `-spotify` command.")
        return
    elif key is None and target is not None:
        await ctx.send("This person does not have Spotify linked to their account. Tell them to link their Spotify "
                       "by using the `-spotify` command.")
        return

    key = key[1]

    sp = spotipy.Spotify(auth=key)

    terms = ["short_term",]

    songs = []

    for term in terms:
        data = sp.current_user_top_tracks(time_range=term)
        for song in data["items"]:
            songs.append(f'{song["artists"][0]["name"]} - {song["name"]}')
        songs = list(set(songs))
        if len(songs) >= 10:
            songs = songs[:10]
            break

    song_count = len(songs)
    if song_count == 0:
        await ctx.send(f"Could not find any recent top songs for {'you' if target is None else 'them'} :(")
        return

    msg = "```"
    for song in songs:
        sq.queue.append(Song(lazy_loaded=True, query=song))
        msg += f'{song}\n'

    if sq.channel != channel:
        await channel.connect()
        sq.channel = channel
    target_name = 'your' if target is None else "**"+target.display_name+"\'s**"
    await ctx.send(f"Added `{song_count}` of {target_name} recent top tracks\n{msg}```")

    if not sq.is_playing:
        sq.current_queue_number = current_queue_length
        play_song(sq, channel)

@ensure_queue()
@is_in_our_vc()
@commands.cooldown(rate=1, per=1, type=BucketType.member)
@client.command(name="top", aliases=["overalltop",])
async def top(ctx: commands.Context, target: typing.Optional[discord.Member] = None):
    sq = server_queues[ctx.guild.id]
    sq.active_text_channel = ctx.channel
    channel = ctx.author.voice.channel
    current_queue_length = len(sq.queue)

    id = ctx.author.id if target is None else target.id
    key = db.getSpotifyKey(id)

    if key is None and target is None:
        await ctx.send("You need to have Spotify linked to use this command. You can link your account"
                       "by using the `-spotify` command.")
        return
    elif key is None and target is not None:
        await ctx.send("This person does not have Spotify linked to their account. Tell them to link their Spotify "
                       "by using the `-spotify` command.")
        return

    key = key[1]

    sp = spotipy.Spotify(auth=key)

    terms = ["long_term",]

    songs = []

    for term in terms:
        data = sp.current_user_top_tracks(time_range=term)
        for song in data["items"]:
            songs.append(f'{song["artists"][0]["name"]} - {song["name"]}')
        songs = list(set(songs))
        if len(songs) >= 10:
            songs = songs[:10]
            break

    song_count = len(songs)
    if song_count == 0:
        await ctx.send(f"Could not find any overall top songs for {'you' if target is None else 'them'} :(")
        return

    msg = "```"
    for song in songs:
        sq.queue.append(Song(lazy_loaded=True, query=song))
        msg += f'{song}\n'

    if sq.channel != channel:
        await channel.connect()
        sq.channel = channel
    target_name = 'your' if target is None else "**"+target.display_name+"\'s**"
    await ctx.send(f"Added `{song_count}` of {target_name} overall top tracks\n{msg}```")

    if not sq.is_playing:
        sq.current_queue_number = current_queue_length
        play_song(sq, channel)


if __name__ == "__main__":
    with open("secrets.json") as file:
        secrets = json.load(file)
        client.run(secrets["discord_bot_token"])
