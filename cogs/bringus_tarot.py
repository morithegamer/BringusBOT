import random
import discord
from discord import app_commands
from discord.ext import commands
from utils import tarot  # if you move the cards there

class Tarot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tarot", description="Draw a random tarot card.")
    async def tarot_card(self, interaction: discord.Interaction):
        card = random.choice(tarot.tarot_cards)
        embed = discord.Embed(
            title=f"{card['emoji']} {card['name']}",
            description=card['meaning'],
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Tarot(bot))
