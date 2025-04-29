import discord
from discord.ext import commands
from discord import app_commands, Interaction

class BringusXP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = {}

    @app_commands.command(name="rank", description="Check your XP rank!")
    async def rank(self, interaction: Interaction):
        user_id = str(interaction.user.id)
        xp = self.data.get(user_id, 0)
        await interaction.response.send_message(f"⭐ You have {xp} XP!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(BringusXP(bot))