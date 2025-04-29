from discord.ext import commands
from discord import app_commands, Interaction

class BringusMemes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="meme", description="Get a random meme!")
    async def meme(self, interaction: Interaction):
        await interaction.response.send_message("Here's a meme! (Add your meme logic)", ephemeral=False)

async def setup(bot):
    await bot.add_cog(BringusMemes(bot))