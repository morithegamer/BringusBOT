import discord
from discord.ext import commands
from discord import app_commands

class StatusManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ssetbotstatus", description="Manually set the bot's status")
    @app_commands.describe(type="online, idle, or dnd", message="The status message")
    async def setstatus(self, interaction: discord.Interaction, type: str, message: str):
        if not interaction.guild:
            await interaction.response.send_message("⛔ This command can only be used in a server.", ephemeral=True)
            return

        member = interaction.guild.get_member(interaction.user.id)
        if not member or not member.guild_permissions.administrator:
            await interaction.response.send_message("⛔ Only admins can use this command!", ephemeral=True)
            return

        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd
        }

        status_type = status_map.get(type.lower())
        if not status_type:
            await interaction.response.send_message("Invalid status type. Choose from `online`, `idle`, or `dnd`.", ephemeral=True)
            return

        activity = discord.Game(name=message)
        await self.bot.change_presence(status=status_type, activity=activity)
        await interaction.response.send_message(f"✅ Status updated to `{type}` with message: `{message}`")

async def setup(bot):
    """
    Adds the StatusManager cog to the bot.
    """
    await bot.add_cog(StatusManager(bot))