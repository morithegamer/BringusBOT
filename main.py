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
bot = commands.Bot(command_prefix="None", intents=intents)

# Load environment variables
TOKEN = os.getenv("DISCORD_TOKEN")
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
        if (
            filename.endswith(".py")
            and not filename.startswith("_")
            and filename != "personality_router.py"  # Exclude utility module
        ):
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
        guild_id = int(os.getenv("GUILD_ID", "0"))
        if guild_id:
            synced = await bot.tree.sync(guild=discord.Object(id=guild_id))
            print(f"[Bringus] Synced {len(synced)} slash commands to your server.")
        else:
            synced = await bot.tree.sync()
            print(f"[Bringus] Synced {len(synced)} global slash commands.")
    except Exception as e:
        print(f"[Bringus] Failed to sync slash commands: {e}")

async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

asyncio.run(main())
# ─────────────────────────────────────────────────────────────────────────────
# Bringus Bot Setup Summary
# ─────────────────────────────────────────────────────────────────────────────
# This bot loads modular cogs, sets a dynamic status, and syncs slash commands.
# It uses environment variables (DISCORD_TOKEN, GUILD_ID, etc.) for config.
# Asyncio ensures performance and startup stability.
# Statuses reflect the bot's personality (e.g., Velvet Room themes).
# Cogs provide easy feature expansion — just drop a .py file in /cogs.
# Designed to be friendly, flexible, and fun for your Discord community.
# Make sure Discord app permissions are properly enabled for full functionality.
# ─────────────────────────────────────────────────────────────────────────────
# This code is a basic setup for a Discord bot using discord.py.

