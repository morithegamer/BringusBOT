from discord.ext import commands
from discord import app_commands, Interaction

class BringusVerify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="verify", description="Verify yourself to access the server!")
    async def verify(self, interaction: Interaction):
        await interaction.response.send_message("You are verified!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(BringusVerify(bot))