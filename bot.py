import json
import math
import re
import threading

import discord
import random

import requests
from discord.ext import commands
from discord.utils import get
from discord import FFmpegPCMAudio
from ServerQueue import ServerQueue
from song_grabber import get_song
from Song import Song
import typing

client = commands.Bot(command_prefix="-")
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
@client.command(name="skip", aliases=["next", "nextsong"])
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
@client.command(name="jump", aliases=["jumpto", "skipto"])
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
@client.command(name="info", aliases=["url", "link"])
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
@client.command(name="remove", aliases=["delete"])
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
            resp += f"{i+1}) ({songs[i].length_formatted}) {songs[i].title_formatted}\n{songs[i].url}\n\n"
        resp += "```"

    await ctx.send(resp)

@is_in_our_vc()
@ensure_queue()
@client.command(name="playresult")
async def playresult(ctx: commands.Context, resultNum: typing.Optional[int] = None):
    if ctx.guild.id not in server_queues:
        server_queues[ctx.guild.id] = ServerQueue(ctx.guild)
    sq = server_queues[ctx.guild.id]
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



if __name__ == "__main__":
    with open("secrets.json") as file:
        secrets = json.load(file)
        client.run(secrets["discord_bot_token"])
