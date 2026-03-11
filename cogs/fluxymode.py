import discord
from discord.ext import commands
from discord import app_commands
from utils import fluxymode

class FluxyModeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="fluxymode", description="Toggle Fluxy Mode on or off.")
    @app_commands.checks.has_permissions(administrator=True)  # Only admins can toggle
    async def fluxymode_toggle(self, interaction: discord.Interaction):
        current = fluxymode.is_fluxy_mode_enabled()
        fluxymode.set_fluxy_mode(not current)

        status = "ACTIVE" if not current else "DISABLED"
        emoji = "⚡" if not current else "🌙"

        embed = discord.Embed(
            title=f"{emoji} Fluxy Mode {status}",
            description=(
                "**Fluxy Mode is now enabled.** Expect glitchy embeds, visual boosts, and full neon output."
                if not current else
                "**Fluxy Mode has been turned off.** Returning to default WebFlux Labs aesthetics."
            ),
            color=discord.Color.from_rgb(137, 66, 245)
        )
        embed.set_footer(text="WebFlux Labs • Core System Upgrade", icon_url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(FluxyModeCog(bot))
