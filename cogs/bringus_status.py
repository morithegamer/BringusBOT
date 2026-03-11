import discord
from discord.ext import commands
from discord import app_commands, Interaction
import aiohttp

class BringusStatus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.up_image_url = "https://cdn.discordapp.com/attachments/555148516708712481/1392857212321271818/1tOgqlb.jpg?ex=68710edd&is=686fbd5d&hm=d9072c90303ae01d5693e2e2cfeac9c04a99ee458ff0a71a3591933ba6aa4ce6&"  # Replace with real direct image URL
        self.down_image_url = "https://cdn.discordapp.com/attachments/555148516708712481/1392862464458227803/6Nm5vpC.png?ex=687113c1&is=686fc241&hm=e73216a9c4a947dfc79204a4efef383ee1ffe972c398d88e886e59cee84a0180&"  # Your spicy funny test image
        self.default_image_url = "https://cdn.discordapp.com/attachments/555148516708712481/1392856866262089768/LYNL8FC.jpg?ex=68710e8a&is=686fbd0a&hm=79093d19f32062938773af64845341ef6a7e868cbd2889e9111a3de66e829f3e&"  # Replace with actual default image link

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

    @app_commands.command(name="statusreset", description="Reset Bringus to the original avatar.")
    async def statusreset(self, interaction: Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get(self.default_image_url) as resp:
                if resp.status != 200:
                    await interaction.response.send_message("❌ Could not download default avatar image.", ephemeral=True)
                    return
                image_bytes = await resp.read()
        try:
            await self.bot.user.edit(avatar=image_bytes)
            await interaction.response.send_message("✅ Avatar reset to default!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Could not reset: `{e}`", ephemeral=True)
            print(f"[Status Reset Error] {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(BringusStatus(bot))
