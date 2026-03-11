import discord
from discord.ext import commands
from discord import app_commands
from utils.vision import describe_image 

class VisionCaption(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="visioncaption", description="Use Vision AI to describe an image with style.")
    @app_commands.describe(image="Upload the image to analyze", mood="calm, funny, chaotic, or dramatic")
    async def visioncaption(self, interaction: discord.Interaction, image: discord.Attachment, mood: str = "funny"):
        await interaction.response.defer()  # show "thinking" message

        try:
            image_bytes = await image.read()
        except Exception:
            await interaction.followup.send("❌ Couldn't read that image.")
            return

        response = await describe_image(image_bytes, mood)
        await interaction.followup.send(f"👁️ **Jon (Bringus) sees...**\n> {response}")

async def setup(bot):
    await bot.add_cog(VisionCaption(bot))
