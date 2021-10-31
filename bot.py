import discord
from discord.ext import commands
from discord.utils import get
import youtube_dl
from discord import FFmpegPCMAudio

client = commands.Bot(command_prefix="-")
server_queues = {}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}
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


class ServerQueue:
    def __init__(self, server):
        self.server = server
        self.is_playing = False
        self.current_queue_number = None
        self.queue = []
        self.channel = None
        self.active_text_channel = None  # the text channel that the bot was most recently talked to in
        self.looping = False

    def current_song(self):
        return self.queue[self.current_queue_number]

class Song:
    def __init__(self, *, url=None):
        self.url = url

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(self.url, download=False)

        self.info_dict = info_dict
        self.title = self.info_dict.get("title", "No Title Found")
        self.length = self.info_dict.get("duration", 0)
        self.length_formatted = f"{round(self.length / 60)}:{str(self.length % 60).zfill(2)}"
        if len(self.title) <= 38:
            title_formatted = self.title + " "*(38-len(self.title))
        else:
            title_formatted = self.title[:35]+"..."
        self.queue_string = f"{title_formatted} {self.length_formatted}"



@client.event
async def on_ready():
    print("Ready.")


@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if client.user.id == member.id and not before.channel is None and after.channel is None:
        sq = server_queues[before.channel.guild.id]
        sq.is_playing = False
        sq.current_queue_number = None
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
    voice.play(FFmpegPCMAudio(sq.current_song().info_dict["url"], **FFMPEG_OPTIONS),
               after=lambda x: on_song_end(sq, channel))


def on_song_end(sq, channel):
    if sq.current_queue_number is None:
        return
    if sq.current_queue_number < len(sq.queue) - 1:
        sq.current_queue_number += 1
    elif not sq.looping and sq.current_queue_number == len(sq.queue) - 1:
        sq.is_playing = False
        return
    elif sq.looping and sq.current_queue_number == len(sq.queue) - 1:
        sq.current_queue_number = 0

    play_song(sq, channel)


@client.command(name="play", aliases=["p"])
async def play(ctx: commands.Context, *, query: str):
    song = Song(url=query)
    if ctx.guild.id not in server_queues:
        server_queues[ctx.guild.id] = ServerQueue(ctx.guild)
    sq = server_queues[ctx.guild.id]
    sq.active_text_channel = ctx.channel
    channel = ctx.author.voice.channel

    sq.queue.append(song)

    if sq.channel != channel:
        await channel.connect()
        sq.channel = channel

    await ctx.send(f"Added {song.title} ({song.length_formatted})")

    if not sq.is_playing:
        sq.current_queue_number = len(sq.queue) - 1
        play_song(sq, channel)


@client.command(name="disconnect", aliases=["dc"])
async def disconnect(ctx: commands.Context):
    await ctx.voice_client.disconnect()


@client.command(name="queue", aliases=["q"])
async def queue(ctx: commands.Context):
    message = "```\n"
    sq = server_queues[ctx.guild.id]
    for i,song in enumerate(sq.queue):
        prefix = " >>> " if sq.current_queue_number == i else "     "
        message += f"{prefix} {i+1}) {sq.queue[i].queue_string}\n"
    message += "```"
    await ctx.send(message)


@client.command(name="nowplaying", aliases=["np"])
async def nowplaying(ctx: commands.Context):
    sq = server_queues[ctx.guild.id]
    song = sq.current_song()
    await ctx.send(f"Now Playing: `{song.title}`\n({song.url})")



with open("token.txt") as file:
    client.run(file.read())
