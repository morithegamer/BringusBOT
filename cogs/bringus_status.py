import discord
from discord.ext import commands
from discord import app_commands, Interaction
import aiohttp

class BringusStatus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.up_image_url = "https://i.imgur.com/N3XyUXa.png"  # Placeholder for UP image
        self.down_image_url = "https://i.imgur.com/UNduLJ0.png"  # Placeholder for DOWN image

    @app_commands.command(name="status", description="Change Bringus profile picture to UP or DOWN mode.")
    @app_commands.describe(state="Choose 'up' or 'down'")
    async def status(self, interaction: Interaction, state: str):
        state = state.lower()
        if state not in ["up", "down"]:
            await interaction.response.send_message("❓ Please specify `up` or `down`.", ephemeral=True)
            return

        image_url = self.up_image_url if state == "up" else self.down_image_url

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    await interaction.response.send_message("❌ Could not download the image.", ephemeral=True)
                    return
                image_bytes = await resp.read()

        try:
            await self.bot.user.edit(avatar=image_bytes)
            await interaction.response.send_message(f"✅ Avatar updated to `{state.upper()}` status!", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message("⚠️ Failed to update avatar.", ephemeral=True)
            print(f"[Status Command Error] {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(BringusStatus(bot))