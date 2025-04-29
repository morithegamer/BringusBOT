import discord
from discord.ext import commands
import asyncio
import os
import json

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

with open('config.json') as f:
    config = json.load(f)

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=555148516708712479))
        print(f"[Bringus] Synced {len(synced)} slash commands to your server!")
    except Exception as e:
        print(f"[Bringus] Sync error: {e}")
    print(f"[Bringus] Logged in as {bot.user}")

async def load():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            await bot.load_extension(f'cogs.{filename[:-3]}')

asyncio.run(load())

bot.run(config['token'])