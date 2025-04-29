import discord
from discord.ext import commands
from discord import app_commands, Interaction
import random

class BringusMemes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="meme", description="Send a random meme!")
    async def meme(self, interaction: Interaction):
        memes = [
            "https://i.imgflip.com/30b1gx.jpg",
            "https://i.imgflip.com/1bij.jpg",
            "https://i.imgur.com/XRkU9Y1.jpeg"
        ]
        await interaction.response.send_message(random.choice(memes))

async def setup(bot):
    await bot.add_cog(BringusMemes(bot))