import os
from typing import Final
from dotenv import load_dotenv
from discord.ext import commands
from discord import Intents
import discord
import yt_dlp as youtube_dl
import asyncio

# Cargar las variables de entorno desde el archivo .env / Load environment variables from .env file
load_dotenv()
TOKEN: Final[str] = os.getenv('DISCORD_TOKEN')

# Configuración de yt_dlp para la descarga y extracción de audio / yt_dlp configuration for audio downloading and extraction
youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'geo_bypass': True,
    'http_chunk_size': 10485760,
}

ffmpeg_options = {
    'before_options': '-nostdin',
    'options': '-vn -af "aresample=async=1" -threads 1 -loglevel panic'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

# Clase para manejar la reproducción de audio / Class to handle audio playback
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# Configuración de los intents y creación del bot / Intents configuration and bot creation
intents = Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Cola de reproducción / Playback queue
queue = []

## ========= Funciones / Functions ==============

def play_next(ctx): # Función para reproducir la siguiente canción en la cola / Function to play the next song in the queue
    if queue:
        next_player = queue.pop(0)
        ctx.voice_client.play(next_player, after=lambda e: play_next(ctx))
        asyncio.run_coroutine_threadsafe(ctx.send(f'Reproduciendo: {next_player.title}'), client.loop)

## ========= Comandos / Commands ===============

@client.command() # Muestra la lista de comandos disponibles / Shows the list of available commands
async def help(ctx):
    help_message = """
    **Available Commands / Comandos Disponibles:**
    1- `!join`: Permite al bot unirse al canal de voz del usuario que lo invoca / Allows the bot to join the voice channel of the invoking user 
    2- `!leave`: Permite al bot salir del canal de voz en el que está actualmente / Allows the bot to leave the current voice channel
    3- `!play <URL>`: Reproduce una canción desde la URL proporcionada. Si ya hay una canción en reproducción, la agrega a la cola / Plays a song from the provided URL. If a song is already playing, it adds it to the queue
    4- `!skip`: Salta a la siguiente canción en la cola / Skips to the next song in the queue
    5- `!pause`: Pausa la canción en reproducción / Pauses the currently playing song 
    6- `!resume`: Reanuda la reproducción si la canción está pausada / Resumes playback if the song is paused
    7- `!stop`: Detiene la reproducción de la canción actual y borra la cola / Stops the current playback and clears the queue
    8- `!help`: Muestra este mensaje / Shows this message
    """
    await ctx.send(help_message)

@client.command() # Comando para unirse a un canal de voz / Command to join a voice channel
async def join(ctx):
    if not ctx.message.author.voice:
        await ctx.send("You must be in a voice channel to use this command. / Debes estar en un canal de voz para usar este comando.")
        return
    channel = ctx.message.author.voice.channel
    await channel.connect()

@client.command() # Comando para salir de un canal de voz / Command to leave a voice channel
async def leave(ctx):
    if not ctx.voice_client:
        await ctx.send("I am not in a voice channel. / No estoy en un canal de voz.")
        return
    await ctx.voice_client.disconnect()

@client.command() # Comando para reproducir una canción desde una URL / Command to play a song from a URL
async def play(ctx, url):
    async with ctx.typing():
        player = await YTDLSource.from_url(url, loop=client.loop, stream=True)
        if ctx.voice_client.is_playing():
            queue.append(player)
            await ctx.send(f'Added to queue: {player.title} / Agregado a la cola: {player.title}')
        else:
            ctx.voice_client.play(player, after=lambda e: play_next(ctx))
            await ctx.send(f'Playing: {player.title} / Reproduciendo: {player.title}')

@client.command() # Comando para saltar a la siguiente canción en la cola / Command to skip to the next song in the queue
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Song skipped. / Canción saltada.")
        play_next(ctx)
    else:
        await ctx.send("There is no song currently playing. / No hay ninguna canción en reproducción.")

@client.command() # Comando para pausar la reproducción actual / Command to pause the current playback
async def pause(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Playback paused. / Reproducción pausada.")
    else:
        await ctx.send("There is no song currently playing. / No hay ninguna canción en reproducción.")

@client.command() # Comando para reanudar la reproducción si está pausada / Command to resume playback if paused
async def resume(ctx):
    if ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Playback resumed. / Reproducción reanudada.")
    else:
        await ctx.send("The song is not paused. / La canción no está pausada.")

@client.command() # Comando para detener la reproducción y vaciar la cola / Command to stop playback and clear the queue
async def stop(ctx):
    ctx.voice_client.stop()
    queue.clear()
    await ctx.send("Playback stopped and queue cleared. / Reproducción detenida y cola vaciada.")

## ============ Eventos / Events ==============

# Evento que se ejecuta cuando el bot está listo / Event triggered when the bot is ready
@client.event
async def on_ready():
    print(f'{client.user.name} is ready! / {client.user.name} está listo!')
    await client.change_presence(activity=discord.Game(name="!help"))

# Verifica que el bot esté en un canal de voz antes de reproducir / Ensure the bot is in a voice channel before playing
@play.before_invoke
async def ensure_voice(ctx):
    if not ctx.voice_client:
        await ctx.invoke(join)

# Ejecutar el bot / Run the bot
client.run(TOKEN)
