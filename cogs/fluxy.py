import discord
from discord import app_commands
from discord.ext import commands
from utils.personality_router import get_persona_prompt
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

# User-specific mood memory
user_moods = {}

# Available mood choices for Fluxy
MOOD_PRESETS = ["friendly", "sassy", "serious", "chaotic"]

class FluxyPersona(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="fluxymood", description="Set Fluxy's personality mood.")
    @app_commands.describe(mood="Select a personality preset for Fluxy.")
    @app_commands.choices(mood=[discord.app_commands.Choice(name=m.title(), value=m) for m in MOOD_PRESETS])
    async def fluxymood(self, interaction: discord.Interaction, mood: str):
        user_moods[interaction.user.id] = mood
        await interaction.response.send_message(f"🎀 Fluxy's mood is now set to **{mood.title()}** for you!", ephemeral=True)

    @app_commands.command(name="ask", description="Ask Fluxy a question!")
    @app_commands.describe(question="What would you like to ask Fluxy?")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer()
        mood = user_moods.get(interaction.user.id, "friendly")
        system_prompt = get_persona_prompt("fluxy", mood)

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}
                ]
            )
            answer = response["choices"][0]["message"]["content"]
            await interaction.followup.send(
                f"🎀 **Fluxy ({mood.title()} Mode)** says:**\n\n{answer}"
            )
        except Exception as e:
            await interaction.followup.send(f"⚠️ Fluxy had a hiccup: `{e}`")

async def setup(bot: commands.Bot):
    await bot.add_cog(FluxyPersona(bot))