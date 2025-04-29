from discord.ext import commands
from discord import app_commands, Interaction

class BringusReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="reactionrole", description="Set up a reaction role!")
    async def reactionrole(self, interaction: Interaction):
        await interaction.response.send_message("Setting up a reaction role! (Add your logic)", ephemeral=True)

async def setup(bot):
    await bot.add_cog(BringusReactionRoles(bot))