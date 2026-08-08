import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import static_ffmpeg
import os
from flask import Flask
from threading import Thread

# Initialize Flask server so Render free tier remains responsive
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_web_server():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web_server).start() 

# ==================== CONFIGURATION BOX ====================
TEST_SERVER_ID = 1529453134634811463  
# ===========================================================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

server_playback_states = {}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch', 
    'source_address': '0.0.0.0',
    'nocheckcertificate': True,
    'extruct': True,
    'http_chunk_size': 1048576,
    'headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn', 
}

@bot.event
async def on_ready():
    # Instantly downloads and extracts standalone Linux FFmpeg paths into the instance environment
    static_ffmpeg.add_paths()
    
    MY_GUILD = discord.Object(id=TEST_SERVER_ID) 
    print(f"🔄 Syncing slash commands instantly to server ID: {TEST_SERVER_ID}...")
    try:
        bot.tree.copy_global_to(guild=MY_GUILD)
        synced_local = await bot.tree.sync(guild=MY_GUILD)
        await bot.tree.sync() 
        print(f"✅ Success! Synced {len(synced_local)} instant server slash commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    print(f"🚀 Active Public Bot: {bot.user.name}!")


async def play_audio_stream(vc, guild_id, search_query):
    """Asynchronous streaming background driver utilizing explicitly localized binary binaries"""
    loop = asyncio.get_event_loop()
    
    # Run the blocking network extraction safely inside an isolated system executor thread
    def extract():
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            return ydl.extract_info(search_query, download=False)
            
    try:
        info = await loop.run_in_executor(None, extract)
        if 'entries' in info and len(info['entries']) > 0:
            video_data = info['entries'][0]
        else:
            video_data = info
        audio_url = video_data['url']
    except Exception as e:
        print(f"Background Extraction Error: {e}")
        return

    def after_playing_finished(error):
        if error:
            print(f"Playback error caught: {error}")
            
        state = server_playback_states.get(guild_id, {"loop_enabled": False, "current_search": search_query})
        if state["loop_enabled"] and vc.is_connected():
            print(f"🔁 Loop active for guild {guild_id}. Restarting audio source stream.")
            # Trigger the next track loop back smoothly inside the asyncio engine loop thread
            asyncio.run_coroutine_threadsafe(play_audio_stream(vc, guild_id, state["current_search"]), loop)

    # Force discord.py to use static-ffmpeg's localized binary string path explicitly
    ffmpeg_binary_path = "ffmpeg"
    vc.play(discord.FFmpegPCMAudio(audio_url, executable=ffmpeg_binary_path, **FFMPEG_OPTIONS), after=after_playing_finished)


# ================== GLOBAL SLASH COMMANDS ==================

@bot.tree.command(name="play", description="Search and stream audio inside your voice channel")
@app_commands.describe(search="Type song title or artist name")
async def play(interaction: discord.Interaction, search: str):
    if not interaction.user.voice:
        await interaction.response.send_message("❌ You must join a voice channel first!", ephemeral=True)
        return

    await interaction.response.defer() # Acknowledges interaction immediately to stop the 3s timeout
    guild_id = interaction.guild_id
    voice_channel = interaction.user.voice.channel

    if interaction.guild.voice_client is None:
        vc = await voice_channel.connect()
    else:
        vc = interaction.guild.voice_client

    server_playback_states[guild_id] = {"loop_enabled": False, "current_search": search}

    loop_loop = asyncio.get_event_loop()
    try:
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = await loop_loop.run_in_executor(
                None, lambda: ydl.extract_info(search, download=False)
            )
            if 'entries' in info and len(info['entries']) > 0:
                video_data = info['entries'][0]
            else:
                video_data = info

            video_title = video_data.get('title', 'Music Video')
            video_url = video_data.get('webpage_url', f"https://youtube.com{video_data.get('id')}")
            
    except Exception as e:
        # Prints out the true technical YouTube blocking error straight to your Render log dashboard terminal
        print(f"❌ TECHNICAL YT-DLP ERROR CAUGHT IN LOGS: {e}")
        await interaction.followup.send("❌ Search Error: Video tracking target broken or blocked.")
        return

    if vc.is_playing():
        vc.stop()

    await play_audio_stream(vc, guild_id, search)

    embed = discord.Embed(
        title=f"🎶 Now Playing: {video_title}",
        description="Streaming audio in your Voice Channel!",
        color=discord.Color.red()
    )
    
    await interaction.followup.send(content=f"🎥 **Video Link:** {video_url}", embed=embed)


@bot.tree.command(name="loop", description="Toggle loop mode ON/OFF for the currently playing song")
async def loop_toggle(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if guild_id not in server_playback_states:
        await interaction.response.send_message("❌ Nothing is playing right now to loop!", ephemeral=True)
        return
        
    current_setting = server_playback_states[guild_id]["loop_enabled"]
    server_playback_states[guild_id]["loop_enabled"] = not current_setting
    new_setting = server_playback_states[guild_id]["loop_enabled"]

    if new_setting:
        await interaction.response.send_message("🔁 **Loop Mode Activated!**")
    else:
        await interaction.response.send_message("➡️ **Loop Mode Deactivated!**")


@bot.tree.command(name="stop", description="Stops the player and disconnects the bot")
async def stop(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if guild_id in server_playback_states:
        server_playback_states[guild_id]["loop_enabled"] = False
        
    vc = interaction.guild.voice_client
    if vc:
        if vc.is_playing():
            vc.stop()
        await vc.disconnect()
        await interaction.response.send_message("👋 **Stopped playback and left the channel!**")
    else:
        await interaction.response.send_message("❌ **I am not inside a voice channel!**", ephemeral=True)

bot.run(os.environ.get('DISCORD_TOKEN'))

