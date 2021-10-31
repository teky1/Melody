import discord
from discord.ext import commands
from discord.utils import get
import youtube_dl
from discord import FFmpegPCMAudio

client = commands.Bot(command_prefix="-")
server_queues = {}


class ServerQueue:
    def __init__(self, server):
        self.server = server
        self.is_playing = False
        self.current_queue_number = None
        self.queue = []
        self.channel = None
        self.looping = False


class Song:
    def __init__(self, *, url=None, query=None, ):
        self.url = url
        self.title = None
        self.length = None


@client.event
async def on_ready():
    print("Ready.")

@client.command(name="test")
async def test(ctx: commands.Context):
    await ctx.reply("Testing, testing, 123")

def play_song(sq, channel):
    sq.is_playing = True
    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn'
    }
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    voice = get(client.voice_clients, channel=channel)
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(sq.queue[sq.current_queue_number].url, download=False)
        voice.play(FFmpegPCMAudio(info["url"], **FFMPEG_OPTIONS),
                   after=lambda x: on_song_end(sq, channel))

def on_song_end(sq, channel):
    if sq.current_queue_number < len(sq.queue)-1:
        sq.current_queue_number += 1
    elif not sq.looping and sq.current_queue_number == len(sq.queue)-1:
        sq.is_playing = False
        return
    elif sq.looping and sq.current_queue_number == len(sq.queue)-1:
        sq.current_queue_number = 0

    play_song(sq, channel)



@client.command(name="play", aliases=["p"])
async def play(ctx: commands.Context, *, query: str):
    song = Song(url=query)
    if ctx.guild.id not in server_queues:
        server_queues[ctx.guild.id] = ServerQueue(ctx.guild)
    sq = server_queues[ctx.guild.id]

    channel = ctx.author.voice.channel

    sq.queue.append(song)

    if sq.channel != channel:
        await channel.connect()
        sq.channel = channel


    if sq.is_playing:
        await ctx.reply("added song")
    else:
        sq.current_queue_number = len(sq.queue)-1
        play_song(sq, channel)














with open("token.txt") as file:
    client.run(file.read())
