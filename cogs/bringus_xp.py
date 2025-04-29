from discord.ext import commands
from discord import app_commands, Interaction

class BringusXP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rank", description="Check your XP rank!")
    async def rank(self, interaction: Interaction):
        await interaction.response.send_message("Your XP rank is 1! (Add real XP system here)", ephemeral=False)

async def setup(bot):
    await bot.add_cog(BringusXP(bot))