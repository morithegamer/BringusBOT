import discord
from discord.ext import commands
from discord import app_commands, Interaction

class BringusPing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Check if Bringus is alive.")
    async def ping(self, interaction: Interaction):
        await interaction.response.send_message("🏓 Pong!")

async def setup(bot):
    await bot.add_cog(BringusPing(bot))