import discord
from discord.ext import commands
from discord import app_commands, Interaction

class BringusReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="reactionrole", description="Create a basic reaction role message.")
    async def reactionrole(self, interaction: Interaction):
        embed = discord.Embed(
            title="🛡️ Reaction Role Setup",
            description="React below to get your role!",
            color=0x7289DA
        )
        channel = interaction.channel
        if isinstance(channel, discord.TextChannel):
            message = await channel.send(embed=embed)
            # Example: react with 🧠 to get a role
            await message.add_reaction("🧠")
            await interaction.response.send_message("✅ Reaction role message created!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ This command can only be used in a text channel.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(BringusReactionRoles(bot))
