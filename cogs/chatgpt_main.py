import discord
from discord.ext import commands
from discord import app_commands
from utils.chatgpt import ask_chatgpt 
import random

class ChatGPTMain(commands.Cog): 
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="askbringus", description="Talk to Jon (Bringus) powered by ChatGPT.")
    @app_commands.describe(
        prompt="What do you want to ask?",
        mood="Choose a mood: calm, chaotic, snarky, poetic, or 'random'"
    )
    async def askbringus(self, interaction: discord.Interaction, prompt: str, mood: str = "chaotic"):
        await interaction.response.defer(thinking=True)

        # Define mood personalities
        moods = {
            "calm": "You are a calm, supportive AI assistant named Jon (Bringus). Be polite and reassuring.",
            "chaotic": "You are a chaotic gremlin AI named Jon (Bringus). Say wild things with snark.",
            "snarky": "You are Jon (Bringus), the snarkiest digital fox alive. Answer sarcastically but smart.",
            "poetic": "You are a poetic AI philosopher named Jon (Bringus). Respond in elegant, gothic prose."
        }

        # Randomize if requested
        selected_mood = mood.lower()
        if selected_mood == "random":
            selected_mood = random.choice(list(moods.keys()))
        system_prompt = moods.get(selected_mood, moods["chaotic"])

        # Get GPT reply
        try:
            reply = await ask_chatgpt(prompt, system_prompt)
        except Exception as e:
            await interaction.followup.send(f"❌ Jon failed to respond: `{e}`")
            return

        # Create embed reply
        embed = discord.Embed(
            title="🧠 Jon (Bringus) Has Spoken",
            description=reply,
            color=discord.Color.from_str("#BC51D2")
        )
        embed.set_footer(text=f"Mood: {selected_mood.capitalize()} | Powered by GPT")

        # Send reply & create a thread
        response = await interaction.followup.send(embed=embed)
        if isinstance(response, discord.Message):
            await response.create_thread(name=f"🧵 {interaction.user.display_name} & Jon", auto_archive_duration=60) # type: ignore

async def setup(bot: commands.Bot):
    await bot.add_cog(ChatGPTMain(bot))
