import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import static_ffmpeg
import os
from flask import Flask
from threading import Thread

# Keep Render Free Tier Awake
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and grooving!"

def run_web_server():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web_server).start() 

# Configuration
TEST_SERVER_ID = 1526293661300817920  

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Global systems dictionary to track state per server (Guild)
server_music_data = {}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'scsearch5',  # Pulls top 5 candidates for fallback stability
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
    static_ffmpeg.add_paths()
    MY_GUILD = discord.Object(id=TEST_SERVER_ID) 
    print(f"🔄 Syncing slash commands...")
    try:
        bot.tree.copy_global_to(guild=MY_GUILD)
        await bot.tree.sync(guild=MY_GUILD)
        await bot.tree.sync() 
        print(f"✅ Success! Keyword matching engines active.")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    print(f"🚀 Active: {bot.user.name}!")

def init_guild_state(guild_id):
    if guild_id not in server_music_data:
        server_music_data[guild_id] = {
            "queue": [],
            "loop_enabled": False,
            "current_track_title": "Nothing playing",
            "current_search": ""
        }

def apply_keyword_filter(user_query: str) -> str:
    """
    Automated Keyword System: Detects raw links vs text queries.
    If it's text, it automatically appends filtering keys to target music tracks.
    """
    if user_query.startswith("http://") or user_query.startswith("https://"):
        return user_query
        
    cleaned_query = user_query.strip().lower()
    keywords_to_add = " track audio"
    
    if any(word in cleaned_query for word in ["remix", "cover", "lyrics", "official", "audio"]):
        return user_query
        
    optimized_search = user_query + keywords_to_add
    print(f"⚙️ Keyword System Optimized Search: '{user_query}' -> '{optimized_search}'")
    return optimized_search

async def check_and_play_next(vc, guild_id):
    state = server_music_data[guild_id]
    if state["loop_enabled"] and state["current_search"]:
        await play_audio_stream(vc, guild_id, state["current_search"])
        return

    if len(state["queue"]) > 0:
        next_track = state["queue"].pop(0)
        state["current_search"] = next_track["url"]
        state["current_track_title"] = next_track["title"]
        await play_audio_stream(vc, guild_id, next_track["url"])
    else:
        state["current_track_title"] = "Nothing playing"
        state["current_search"] = ""

async def play_audio_stream(vc, guild_id, audio_target):
    loop = asyncio.get_event_loop()
    
    def extract():
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            return ydl.extract_info(audio_target, download=False)
            
    try:
        info = await loop.run_in_executor(None, extract)
        if 'entries' in info and len(info['entries']) > 0:
            video_data = info['entries']
        else:
            video_data = info
        audio_url = video_data['url']
    except Exception as e:
        print(f"Background Extraction Error: {e}")
        return

    def after_playing_finished(error):
        if error:
            print(f"Playback error: {error}")
        if vc.is_connected():
            asyncio.run_coroutine_threadsafe(check_and_play_next(vc, guild_id), loop)

    if vc.is_playing():
        vc.stop()
        
    vc.play(discord.FFmpegPCMAudio(audio_url, executable="ffmpeg", **FFMPEG_OPTIONS), after=after_playing_finished)

# ================== GLOBAL SLASH COMMANDS ==================

@bot.tree.command(name="play", description="Add a track link or song name to the active music queue")
@app_commands.describe(search="Paste direct link or type title")
async def play(interaction: discord.Interaction, search: str):
    if not interaction.user.voice:
        await interaction.response.send_message("❌ You must join a voice channel first!", ephemeral=True)
        return

    await interaction.response.defer()
    guild_id = interaction.guild_id
    init_guild_state(guild_id)
    state = server_music_data[guild_id]
    
    voice_channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client or await voice_channel.connect()

    processed_search_query = apply_keyword_filter(search)

    loop_loop = asyncio.get_event_loop()
    try:
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = await loop_loop.run_in_executor(None, lambda: ydl.extract_info(processed_search_query, download=False))
            
            if 'entries' in info and len(info['entries']) > 0:
                video_data = None
                for entry in info['entries']:
                    if entry and 'url' in entry:
                        video_data = entry
                        break
                if not video_data:
                    raise Exception("No playable audio configurations found.")
            else:
                video_data = info

            video_title = video_data.get('title', 'Music Stream')
            video_url = video_data.get('webpage_url', search)
            
    except Exception as e:
        print(f"❌ TECHNICAL YT-DLP ERROR CAUGHT IN LOGS: {e}")
        await interaction.followup.send("❌ Search Error: Could not resolve music track. Try pasting a direct link!")
        return

    if vc.is_playing() or vc.is_paused():
        state["queue"].append({"title": video_title, "url": video_data['url']})
        embed = discord.Embed(
            title=f"📥 Added to Queue (Position #{len(state['queue'])})",
            description=f"**[{video_title}]({video_url})** will play next!",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)
    else:
        state["current_track_title"] = video_title
        state["current_search"] = video_data['url']
        await play_audio_stream(vc, guild_id, video_data['url'])
        
        embed = discord.Embed(
            title=f"🎶 Now Playing",
            description=f"**[{video_title}]({video_url})**",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="pause", description="Pause the current song")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ **Playback paused.** Use `/resume` to continue.")
    else:
        await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

@bot.tree.command(name="resume", description="Resume the paused song")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ **Playback resumed!**")
    else:
        await interaction.response.send_message("❌ Audio is not paused.", ephemeral=True)

@bot.tree.command(name="skip", description="Skip the current song and play the next one in queue")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    guild_id = interaction.guild_id
    init_guild_state(guild_id)
    
    if vc and (vc.is_playing() or vc.is_paused()):
        server_music_data[guild_id]["loop_enabled"] = False
        vc.stop()
        await interaction.response.send_message("⏩ **Skipped the current track!**")
    else:
        await interaction.response.send_message("❌ Nothing is playing to skip.", ephemeral=True)

@bot.tree.command(name="viewqueue", description="View all upcoming tracks in the music list")
async def view_queue(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    init_guild_state(guild_id)
    state = server_music_data[guild_id]

    embed = discord.Embed(title="📋 Server Music Queue", color=discord.Color.orange())
    embed.add_field(name="🎧 Currently Playing", value=f"`{state['current_track_title']}`", inline=False)
    
    queue_text = ""
    if len(state["queue"]) == 0:
        queue_text = "The queue is completely empty! Add tracks with `/play`."
    else:
        for index, track in enumerate(state["queue"], start=1):
            queue_text += f"**{index}.** `{track['title']}`\n"
            
    embed.add_field(name="⏳ Up Next", value=queue_text, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="loop", description="Toggle loop mode ON/OFF for the current song")
async def loop_toggle(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    init_guild_state(guild_id)
    state = server_music_data[guild_id]
    
    state["loop_enabled"] = not state["loop_enabled"]
    if state["loop_enabled"]:
        await interaction.response.send_message("🔁 **Loop Mode Activated!** Current song will repeat.")
    else:
        await interaction.response.send_message("➡️ **Loop Mode Deactivated!** Queue will proceed normally.")

@bot.tree.command(name="stop", description="Clear the entire queue and disconnect from voice")
async def stop(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if guild_id in server_music_data:
        server_music_data[guild_id]["queue"] = []
        server_music_data[guild_id]["loop_enabled"] = False
        server_music_data[guild_id]["current_track_title"] = "Nothing playing"
        server_music_data[guild_id]["current_search"] = ""
        
    vc = interaction.guild.voice_client
    if vc:
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        await vc.disconnect()
        await interaction.response.send_message("👋 **Cleared queue and left the channel!**")
    else:
        await interaction.response.send_message("❌ I'm not in a voice channel.", ephemeral=True)

bot.run(os.environ.get('DISCORD_TOKEN'))


