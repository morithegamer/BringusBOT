import discord
from discord import app_commands
from discord.ext import commands
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

user_modes = {}

def get_prompt_for_mode(mode, username):
    if mode == "standard":
        return [
            {"role": "system", "content": "You are a professional tarot reader. Draw a real tarot card from the Major Arcana. Respond with the card name, meaning, and a mystical but serious interpretation."},
            {"role": "user", "content": f"Draw a tarot card for {username}."}
        ]
    elif mode == "meme":
        return [
            {"role": "system", "content": "You are Bringus the Seer, a chaotic meme tarot reader. Create a ridiculous or real tarot card and give a dramatic, funny fortune."},
            {"role": "user", "content": f"Give a meme tarot reading for {username}."}
        ]
    else:
        return [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"Hello, what is my tarot reading?"}
        ]

class TarotWithMode(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setmode", description="Set your tarot reading mode (standard or meme)")
    @app_commands.describe(mode="Choose either 'standard' or 'meme'")
    async def setmode(self, interaction: discord.Interaction, mode: str):
        if mode not in ["standard", "meme"]:
            await interaction.response.send_message("Invalid mode. Please choose 'standard' or 'meme'.", ephemeral=True)
            return
        user_modes[interaction.user.id] = mode
        await interaction.response.send_message(f"Tarot mode set to **{mode}** for {interaction.user.display_name}.", ephemeral=True)

    @app_commands.command(name="tarotmode", description="Draw a tarot card based on your selected mode.")
    async def tarot(self, interaction: discord.Interaction):
        mode = user_modes.get(interaction.user.id, "standard")
        await interaction.response.defer()
        prompt = get_prompt_for_mode(mode, interaction.user.display_name)
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=prompt
            )
            answer = response["choices"][0]["message"]["content"]
            embed = discord.Embed(
                title=f"🔮 {mode.title()} Tarot Reading for {interaction.user.display_name}",
                description=answer,
                color=discord.Color.purple()
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to get a tarot reading: `{e}`")

async def setup(bot):
    await bot.add_cog(TarotWithMode(bot))
