import discord
from discord.ext import commands
from discord import app_commands
from utils.debuglog import log  # Optional: if you want logging

class AdminResync(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="resynccommands", description="Force re-sync all slash commands (Owner only).")
    async def resync_commands(self, interaction: discord.Interaction):
        # Optional: put your user ID(s) here
        if interaction.user.id not in [785194743293673493]:  
            await interaction.response.send_message("❌ You aren't allowed to use this command.", ephemeral=True)
            return
        
        try:
            await self.bot.tree.sync(guild=interaction.guild)
            await interaction.response.send_message("✅ Slash commands have been force re-synced!", ephemeral=True)
            log("admin", "Slash commands re-synced via /resynccommands")
        except Exception as e:
            await interaction.response.send_message(f"⚠️ Resync failed: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminResync(bot))
