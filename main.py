import discord
from discord.ext import commands
import asyncio
import os
import random

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

TOKEN = os.getenv("TOKEN")
PUBLIC_WEBHOOK = os.getenv("PUBLIC_WEBHOOK")
STAFF_WEBHOOK = os.getenv("STAFF_WEBHOOK")

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=555148516708712479))
        print(f"[Bringus] Synced {len(synced)} slash commands to your server!")
    except Exception as e:
        print(f"[Bringus] Sync error: {e}")

    statuses = [
        discord.Game(name="Counting memes! 🤖"),
        discord.Game(name="Watching the Velvet Room visitors... 💎"),
        discord.Activity(type=discord.ActivityType.watching, name="the fate of memers"),
        discord.Activity(type=discord.ActivityType.listening, name="the whispers of Persona users ✨")
    ]

    selected_status = random.choice(statuses)
    await bot.change_presence(status=discord.Status.online, activity=selected_status)

    print(f"[Bringus] Logged in as {bot.user} | Current Status: {selected_status.name}")

async def load():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            await bot.load_extension(f'cogs.{filename[:-3]}')

asyncio.run(load())

bot.run(TOKEN)

