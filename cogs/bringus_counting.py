from discord.ext import commands
from discord import app_commands, Interaction

class BringusCounting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="count", description="Play the counting game!")
    async def count(self, interaction: Interaction):
        await interaction.response.send_message(f"{interaction.user.mention} counted!", ephemeral=False)

async def setup(bot):
    await bot.add_cog(BringusCounting(bot))