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

async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            cog_name = filename[:-3]
            try:
                await bot.load_extension(f"cogs.{cog_name}")
                print(f"[Bringus] Loaded cog: {cog_name}")
            except Exception as e:
                print(f"[Bringus] Failed to load cog {cog_name}: {e}")

@bot.event
async def on_ready():
    print(f"[Bringus] Logged in as {bot.user}")

    # Set random status
    selected_status = random.choice(status_options)
    await bot.change_presence(status=discord.Status.online, activity=selected_status)
    print(f"[Bringus] Status set to: {selected_status.name}")

    # AFTER bot is ready, sync slash commands
    try:
        guild_id = 555148516708712479  # Your real server ID
        synced = await bot.tree.sync(guild=discord.Object(id=guild_id))
        print(f"[Bringus] Synced {len(synced)} slash commands to your server.")
    except Exception as e:
        print(f"[Bringus] Failed to sync slash commands: {e}")

async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

asyncio.run(main())

