import os
from typing import Final
from dotenv import load_dotenv
from discord.ext import commands
from discord import Intents, Embed
import discord
import yt_dlp as youtube_dl
import asyncio
from pytube import Search
import re
from gtts import gTTS

# Cargar las variables de entorno desde el archivo .env
load_dotenv()
TOKEN: Final[str] = os.getenv('DISCORD_TOKEN')

# Configuración de yt_dlp para la descarga y extracción de audio
youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': 'audio/%(extractor)s-%(id)s-%(title)s.%(ext)s',
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
    'options': '-vn -loglevel panic'
}
ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

# Asegurarse de que la carpeta "audio" exista
if not os.path.exists("audio"):
    os.makedirs("audio")

# Clase para manejar la reproducción de audio
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.filename = ytdl.prepare_filename(data)  # Guardar el nombre del archivo para eliminarlo después

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
    
    def cleanup(self):  # Eliminar el archivo después de reproducirlo
        if self.filename and os.path.exists(self.filename):
            os.remove(self.filename)
    
# Configuración de los intents y creación del bot / Intents configuration and bot creation
intents = Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix='d!', intents=intents, help_command=None)

# Cola de reproducción / Playback queue
queue = []

## ========= Funciones / Functions ==============

def send_embed(ctx, title, description):
    embed = Embed(title=title, description=description, color=discord.Color.blurple())
    return ctx.send(embed=embed)

def play_next(ctx):  # Función para reproducir la siguiente canción en la cola
    if queue:
        next_player = queue.pop(0)
        ctx.voice_client.play(next_player, after=lambda e: cleanup_and_play_next(ctx, next_player))
        asyncio.run_coroutine_threadsafe(
            send_embed(ctx, 'Reproduciendo', next_player.title), client.loop)

def on_song_end(ctx, player): # Función para manejar el final de una canción
    # Eliminar el archivo de audio después de la reproducción
    try:
        os.remove(player.filename)
        print(f"Archivo eliminado: {player.filename}")
    except Exception as e:
        print(f"Error al eliminar archivo: {e}")
    # Reproducir la siguiente canción
    play_next(ctx)

async def search_song(query): # Buscar la canción en YouTube usando pytube / Search for the song on YouTube using pytube
    s = Search(query)
    result = s.results
    if result:
        return f'https://www.youtube.com/watch?v={result[0].video_id}'
    return None

def cleanup_and_play_next(ctx, player):  # Borra el archivo del audio y reproducir la siguiente canción
    player.cleanup()
    play_next(ctx)

def is_url(string): # Comprobar si el string es una URL / Check if the string is a URL
    return re.match(r'^(http|https)://', string) is not None

## ========= Comandos / Commands ===============

@client.command() # Muestra la lista de comandos disponibles / Shows the list of available commands
async def help(ctx):
    help_message = """
    **Available Commands / Comandos Disponibles:**
    1- `!join`: Permite al bot unirse al canal de voz del usuario que lo invoca / Allows the bot to join the voice channel of the invoking user 
    2- `!leave`: Permite al bot salir del canal de voz en el que está actualmente / Allows the bot to leave the current voice channel
    3- `!play <song_name_or_URL>`: Busca y reproduce una canción desde YouTube basada en el nombre o URL proporcionado. Si ya hay una canción en reproducción, la agrega a la cola / Search and play a song from YouTube based on the name or URL provided. If a song is already playing, adds it to the queue
    4- `!skip`: Salta a la siguiente canción en la cola / Skips to the next song in the queue
    5- `!pause`: Pausa la canción en reproducción / Pauses the currently playing song 
    6- `!resume`: Reanuda la reproducción si la canción está pausada / Resumes playback if the song is paused
    7- `!stop`: Detiene la reproducción de la canción actual y borra la cola / Stops the current playback and clears the queue
    8- `!speak <text>`: Convierte el texto a voz y lo reproduce en el canal de voz / Converts text to speech and plays it in the voice channel
    9- `!setprefix`: Puedes cambiar el prefijo del bot. Requiere permisos para Gestionar Servidor / You can change the bot prefix. Requires permissions for Manage Guild
    10- `!help`: Muestra este mensaje / Shows this message
    """
    await send_embed(ctx, 'Comandos Disponibles', help_message)

@client.command() # Cambia el prefijo del bot / Changes the bot´s prefix
async def setprefix(ctx, new_prefix: str):
    # Verifica si el usuario tiene permisos para cambiar el prefijo / Check if the user has permissions to change the prefix
    if ctx.author.guild_permissions.manage_guild:
        # Actualiza el prefijo / Update the prefix
        client.command_prefix = new_prefix
        await send_embed(ctx, 'Prefijo Actualizado', f"Prefijo actualizado a: {new_prefix} / Prefix updated to: {new_prefix}")
    else:
        await send_embed(ctx, 'Permisos Denegados', "No tienes permisos para cambiar el prefijo. / You do not have permissions to change the prefix.")

@client.command() # Comando para unirse a un canal de voz / Command to join a voice channel
async def join(ctx):
    if not ctx.message.author.voice:
        await send_embed(ctx, 'Error', "Debes estar en un canal de voz para usar este comando / You must be in a voice channel to use this command")
        return
    channel = ctx.message.author.voice.channel
    await channel.connect()

@client.command()  # Comando para salir de un canal de voz y limpiar archivos
async def leave(ctx):
    if not ctx.voice_client:
        await send_embed(ctx, 'Error', "No estoy en un canal de voz / I am not in a voice channel")
        return
    
    # Limpiar archivos de error en la carpeta "audio"
    audio_folder = "audio"
    if os.path.exists(audio_folder):
        for filename in os.listdir(audio_folder):
            file_path = os.path.join(audio_folder, filename)
            try:
                os.remove(file_path)
                print(f"Archivo eliminado: {file_path}")
            except Exception as e:
                print(f"No se pudo eliminar {file_path}: {e}")
    
    await ctx.voice_client.disconnect()
    await send_embed(ctx, 'Desconectado', "Me he desconectado del canal de voz / Disconnected from the voice channel")

@client.command()  # Comando para reproducir una canción desde una URL o nombre de canción
async def play(ctx, *, search: str):
    async with ctx.typing():
        if is_url(search):
            url = search
        else:
            url = await search_song(search)
            if not url:
                await send_embed(ctx, 'No Encontrado', "No se encontró ninguna canción / No song found")
                return
        
        player = await YTDLSource.from_url(url, loop=client.loop, stream=False)
        if ctx.voice_client.is_playing():
            queue.append(player)
            await send_embed(ctx, 'Agregado a la Cola', f'Agregado a la cola: {player.title} / Added to queue: {player.title}')
        else:
            ctx.voice_client.play(player, after=lambda e: cleanup_and_play_next(ctx, player))
            await send_embed(ctx, 'Reproduciendo', f'Reproduciendo: {player.title} / Playing: {player.title}')

@client.command() # Comando para saltar a la siguiente canción en la cola / Command to skip to the next song in the queue
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await send_embed(ctx, 'Canción Saltada', "Canción saltada / Song skipped")
        play_next(ctx)
    else:
        await send_embed(ctx, 'Nada Reproduciendo', "No hay ninguna canción en reproducción / There is no song currently playing")

@client.command() # Comando para pausar la reproducción actual / Command to pause the current playback
async def pause(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await send_embed(ctx, 'Pausado', "Reproducción pausada / Playback paused")
    else:
        await send_embed(ctx, 'Nada Reproduciendo', "No hay ninguna canción en reproducción / There is no song currently playing")

@client.command() # Comando para reanudar la reproducción si está pausada / Command to resume playback if paused
async def resume(ctx):
    if ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await send_embed(ctx, 'Reanudado', "Reproducción reanudada / Playback resumed")
    else:
        await send_embed(ctx, 'No Pausado', "La canción no está pausada / The song is not paused")

@client.command() # Comando para detener la reproducción y vaciar la cola / Command to stop playback and clear the queue
async def stop(ctx):
    ctx.voice_client.stop()
    queue.clear()
    await send_embed(ctx, 'Detenido', "Reproducción detenida y cola vaciada / Playback stopped and queue cleared")

@client.command()  # Comando para convertir texto a voz y reproducirlo en el canal de voz / Command to convert text to speech and play it on the voice channel
async def speak(ctx, *, text: str):
    if ctx.voice_client:
        # Generar el archivo de audio y guardarlo en la carpeta "audio"
        tts = gTTS(text=text, lang='es')
        tts_filename = 'audio/tts.mp3'
        tts.save(tts_filename)

        # Reproducir el archivo de audio y eliminarlo después de reproducirlo
        ctx.voice_client.play(discord.FFmpegPCMAudio(tts_filename), after=lambda e: os.remove(tts_filename))
        await send_embed(ctx, 'Texto a Voz', f"{ctx.author.mention} via TTS: {text}")
    else:
        await send_embed(ctx, 'Error', "Primero debes invitarme a un canal de voz usando !join / You must first invite me to a voice channel using !join")

## ============ Eventos / Events ==============

# Evento que se ejecuta cuando el bot está listo / Event triggered when the bot is ready
@client.event
async def on_ready():
    print(f'{client.user.name} está listo! / {client.user.name} is ready!')
    await client.change_presence(activity=discord.Game(name="!help || @lostdou"))

# Verifica si el bot es sacado de la llamada para limpiar la carpeta audio
@client.event
async def on_voice_state_update(member, before, after):
    if member == client.user and before.channel is not None and after.channel is None:
        audio_folder = "audio"
        if os.path.exists(audio_folder):
            for filename in os.listdir(audio_folder):
                file_path = os.path.join(audio_folder, filename)
                try:
                    os.remove(file_path)
                    print(f"Archivo eliminado: {file_path}")
                except Exception as e:
                    print(f"No se pudo eliminar {file_path}: {e}")
        print("El bot fue desconectado del canal de voz.")

# Verifica que el bot esté en un canal de voz antes de reproducir / Ensure the bot is in a voice channel before playing
@play.before_invoke
async def ensure_voice(ctx):
    if not ctx.voice_client:
        await ctx.invoke(join)

# Ejecutar el bot / Run the bot
client.run(TOKEN)
