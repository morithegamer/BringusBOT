import discord
from discord.ext import commands
import asyncio
import os
import random

# Setup intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Bot setup
bot = commands.Bot(command_prefix="!", intents=intents)

# Load environment variables
TOKEN = os.getenv("TOKEN")
PUBLIC_WEBHOOK = os.getenv("PUBLIC_WEBHOOK")
STAFF_WEBHOOK = os.getenv("STAFF_WEBHOOK")

# Status list for Bringus + Velvet Room
status_options = [
    discord.Game(name="Counting memes! 🤖"),
    discord.Game(name="Watching Velvet Room visitors 💎"),
    discord.Activity(type=discord.ActivityType.watching, name="fate changing..."),
    discord.Activity(type=discord.ActivityType.listening, name="the whispers of memers ✨")
]

@bot.event
async def on_ready():
    guild_id = 555148516708712479  # Your real server ID

    # Sync slash commands
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=guild_id))
        print(f"[Bringus] Synced {len(synced)} commands to your server.")
    except Exception as e:
        print(f"[Bringus] Initial sync failed: {e}")
        print("[Bringus] Retrying sync in 10 seconds...")
        await asyncio.sleep(10)
        try:
            synced = await bot.tree.sync(guild=discord.Object(id=guild_id))
            print(f"[Bringus] Synced {len(synced)} commands on retry.")
        except Exception as final_error:
            print(f"[Bringus] FINAL SYNC FAILED: {final_error}")

    # Set random status
    selected_status = random.choice(status_options)
    await bot.change_presence(status=discord.Status.online, activity=selected_status)

    print(f"[Bringus] Logged in as {bot.user} | Status: {selected_status.name}")

async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            print(f"[Bringus] Loaded cog: {filename}")

asyncio.run(load_cogs())

# Run bot
bot.run(TOKEN)
