import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import static_ffmpeg
import os

# ==================== CONFIGURATION BOX ====================
# Tell your owner to change this number to whatever server ID she wants to use!
TEST_SERVER_ID = 1529453134634811463  
# ===========================================================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Global tracking system for the song loop state per server
server_playback_states = {}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch', 
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn', 
}

@bot.event
async def on_ready():
    # Instantly points python to the cloud-managed FFmpeg execution tools
    static_ffmpeg.add_paths()
    
    # Reads the server configuration ID number from the box above
    MY_GUILD = discord.Object(id=TEST_SERVER_ID) 
    
    print(f"🔄 Syncing slash commands instantly to server ID: {TEST_SERVER_ID}...")
    try:
        # Forces instant registration to your targeted server layout
        bot.tree.copy_global_to(guild=MY_GUILD)
        synced_local = await bot.tree.sync(guild=MY_GUILD)
        
        # Also registers globally for other servers in the background
        await bot.tree.sync() 
        print(f"✅ Success! Synced {len(synced_local)} instant server slash commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    print(f"🚀 Active Public Bot: {bot.user.name}!")


def play_audio_stream(vc, guild_id, search_query):
    """Core tracking background loop engine that handles repeating if enabled"""
    loop = asyncio.get_event_loop()
    
    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
        try:
            info = ydl.extract_info(search_query, download=False)
            if 'entries' in info and len(info['entries']) > 0:
                video_data = info['entries']
            else:
                video_data = info
            audio_url = video_data['url']
        except Exception as e:
            print(f"Background Extraction Error on loop step: {e}")
            return

    def after_playing_finished(error):
        if error:
            print(f"Playback error caught: {error}")
            
        state = server_playback_states.get(guild_id, {"loop_enabled": False, "current_search": search_query})
        
        if state["loop_enabled"] and vc.is_connected():
            print(f"🔁 Loop active for guild {guild_id}. Restarting audio source stream.")
            play_audio_stream(vc, guild_id, state["current_search"])

    vc.play(discord.FFmpegPCMAudio(audio_url, executable="ffmpeg", **FFMPEG_OPTIONS), after=after_playing_finished)


# ================== GLOBAL SLASH COMMANDS ==================

@bot.tree.command(name="play", description="Search, stream audio inside VC, and spawn inline video player")
@app_commands.describe(search="Type song title or artist name")
async def play(interaction: discord.Interaction, search: str):
    if not interaction.user.voice:
        await interaction.response.send_message("❌ You must join a voice channel first!", ephemeral=True)
        return

    await interaction.response.defer()
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
                video_data = info['entries']
            else:
                video_data = info

            video_title = video_data.get('title', 'Music Video')
            video_url = video_data.get('webpage_url', f"https://youtube.com{video_data.get('id')}")
            
    except Exception as e:
        await interaction.followup.send("❌ Search Error: Video tracking target broken or blocked.")
        return

    if vc.is_playing():
        vc.stop()

    play_audio_stream(vc, guild_id, search)

    embed = discord.Embed(
        title=f"🎶 Now Playing: {video_title}",
        description="Streaming audio in your Voice Channel!\nClick the integrated video layout block below to watch the track.",
        color=discord.Color.red()
    )
    
    await interaction.followup.send(content=f"🎥 **Video Player Link:** {video_url}", embed=embed)


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
        await interaction.response.send_message("🔁 **Loop Mode Activated!** The current music track will repeat forever.")
    else:
        await interaction.response.send_message("➡️ **Loop Mode Deactivated!** Track repetition turned off.")


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
        await interaction.response.send_message("👋 **Stopped playback, cleared loop data, and left the channel!**")
    else:
        await interaction.response.send_message("❌ **I am not currently inside a voice channel here!**", ephemeral=True)

# Securely pulls the bot token out of the cloud hosting dashboard environment
bot.run(os.environ.get('DISCORD_TOKEN'))

