import discord
from discord.ext import commands
from discord.utils import get
from discord import FFmpegPCMAudio
from ServerQueue import ServerQueue
from song_grabber import get_song
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


@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if client.user.id == member.id and before.channel is not None and after.channel is None:
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
    elif sq.current_queue_number < len(sq.queue) - 1:
        sq.current_queue_number += 1
    elif not sq.looping and sq.current_queue_number == len(sq.queue) - 1:
        sq.is_playing = False
        return
    elif sq.looping and sq.current_queue_number == len(sq.queue) - 1:
        sq.current_queue_number = 0

    play_song(sq, channel)


@client.command(name="play", aliases=["p"])
async def play(ctx: commands.Context, *, query: str):
    if ctx.guild.id not in server_queues:
        server_queues[ctx.guild.id] = ServerQueue(ctx.guild)
    sq = server_queues[ctx.guild.id]
    sq.active_text_channel = ctx.channel
    channel = ctx.author.voice.channel

    current_queue_length = len(sq.queue)

    song = get_song(query, sq)

    if song is False:
        await ctx.send("Invalid song.")

    if sq.channel != channel:
        await channel.connect()
        sq.channel = channel

    await ctx.send(f"Added `{song.title}` ({song.length_formatted})")

    if not sq.is_playing:
        sq.current_queue_number = current_queue_length
        play_song(sq, channel)


@client.command(name="disconnect", aliases=["dc", "die"])
async def disconnect(ctx: commands.Context):
    await ctx.voice_client.disconnect()


@client.command(name="queue", aliases=["q"])
async def queue(ctx: commands.Context):
    message = "```\n"
    sq = server_queues[ctx.guild.id]
    for i, song in enumerate(sq.queue):
        prefix = " >>> " if sq.current_queue_number == i else "     "
        message += f"{prefix} {i+1}) {sq.queue[i].queue_string}\n"
    message += "```"
    await ctx.send(message)


@client.command(name="skip", aliases=["next", "nextsong", ""])
async def skip(ctx: commands, amount: typing.Optional[int] = 1):
    if ctx.message.author.voice.channel == ctx.voice_client.channel:
        vc = ctx.author.voice.channel
        ctx.voice_client.stop()
        sq = server_queues[ctx.guild.id]
        sq.active_text_channel = ctx.channel
        curr_queue_num = sq.current_queue_number if sq.current_queue_number is not None else 0
        if curr_queue_num + amount >= len(sq.queue):
            await ctx.send("There's no song to skip to there")
        sq.current_queue_number += amount
        play_song(sq, channel=sq.channel)
        sq.current_queue_number -= 1


@client.command(name="nowplaying", aliases=["np"])
async def nowplaying(ctx: commands.Context):
    sq = server_queues[ctx.guild.id]
    song = sq.current_song()
    await ctx.send(f"Now Playing: `{song.title}`\n({song.url})")

if __name__ == "__main__":
    with open("token.txt") as file:
        client.run(file.read())
