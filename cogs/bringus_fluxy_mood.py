import discord
from discord import app_commands
from discord.ext import commands
from openai import OpenAI
import os

# Create OpenAI client (new SDK way)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Simple user mood memory
user_moods = {}

MOOD_PRESETS = {
    "friendly": "You are Fluxy, a friendly and sweet assistant. You speak gently and kindly.",
    "sassy": "You are Fluxy, a smart and sassy assistant who gives witty and bold replies.",
    "serious": "You are Fluxy, a calm, intelligent assistant. You answer professionally and clearly.",
    "chaotic": "You are Fluxy, an unpredictable and fun assistant who blends humor with helpfulness."
}

class FluxyPersona(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="fluxymood", description="Set Fluxy's mood")
    @app_commands.describe(mood="Choose Fluxy's personality")
    @app_commands.choices(mood=[
        discord.app_commands.Choice(name="Friendly", value="friendly"),
        discord.app_commands.Choice(name="Sassy", value="sassy"),
        discord.app_commands.Choice(name="Serious", value="serious"),
        discord.app_commands.Choice(name="Chaotic", value="chaotic")
    ])
    async def fluxymood(self, interaction: discord.Interaction, mood: str):
        user_moods[interaction.user.id] = mood
        await interaction.response.send_message(f"💫 Fluxy's mood is now set to **{mood.title()}** for you.", ephemeral=True)

    @app_commands.command(name="ask", description="Ask Fluxy a question!")
    @app_commands.describe(question="What would you like to ask?")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer()
        mood = user_moods.get(interaction.user.id, "friendly")
        system_prompt = MOOD_PRESETS.get(mood, MOOD_PRESETS["friendly"])

        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}
                ]
            )
            answer = response.choices[0].message.content
            await interaction.followup.send(
                f"🎀 **Fluxy ({mood.title()} Mode)** says:**\n\n{answer}"
            )
        except Exception as e:
            await interaction.followup.send(f"⚠️ Fluxy had a moment: {e}")

async def setup(bot):
    await bot.add_cog(FluxyPersona(bot))
