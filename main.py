# Bringus Bot Main Starter
import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Velvet Travelers arrive..."))
    from cogs.bringus_verify import VerifyView
    bot.add_view(VerifyView())

    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and filename != "__init__.py":
            await bot.load_extension(f'cogs.{filename[:-3]}')

bot.run("MTM0NjI1MTQ1NTc2NTU0OTEzOA.GvAIcI.S-zhk5fQyt2QRv-EjgWJF88r-mtNeYABg2xtEk")
