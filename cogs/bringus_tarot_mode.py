import discord
from discord import app_commands
from discord.ext import commands
from discord import Interaction
from openai import OpenAI
import os
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

# Setup OpenAI client using latest SDK
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# In-memory tracking of user tarot modes
user_modes = {}

def get_prompt_for_mode(mode, username):
    if mode == "standard":
        return [
            ChatCompletionSystemMessageParam(role="system", content="You are a professional tarot reader. Draw a real tarot card from the Major Arcana. Respond with the card name, meaning, and a mystical but serious interpretation."),
            ChatCompletionUserMessageParam(role="user", content=f"Draw a tarot card for {username}.")
        ]
    elif mode == "meme":
        return [
            ChatCompletionSystemMessageParam(role="system", content="You are Bringus the Seer, a chaotic meme tarot reader. Create a ridiculous or real tarot card and give a dramatic, funny fortune."),
            ChatCompletionUserMessageParam(role="user", content=f"Give a meme tarot reading for {username}.")
        ]
    else:
        return [
            ChatCompletionSystemMessageParam(role="system", content="You are a helpful assistant."),
            ChatCompletionUserMessageParam(role="user", content=f"Hello, what is my tarot reading?")
        ]

class TarotWithMode(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="settarotmode", description="Set your tarot reading mode (standard or meme)")
    @app_commands.describe(mode="Choose either 'standard' or 'meme'")
    async def settarotmode(self, interaction: discord.Interaction, mode: str):
        if mode not in ["standard", "meme"]:
            await interaction.response.send_message("❌ Invalid mode. Choose 'standard' or 'meme'.", ephemeral=True)
            return
        user_modes[interaction.user.id] = mode
        await interaction.response.send_message(f"✅ Tarot mode set to **{mode}** for {interaction.user.display_name}.", ephemeral=True)

    @app_commands.command(name="modetarot", description="Draw a tarot card based on your selected mode.")
    async def modetarot(self, interaction: discord.Interaction):
        mode = user_modes.get(interaction.user.id, "standard")
        await interaction.response.defer()
        prompt = get_prompt_for_mode(mode, interaction.user.display_name)
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=prompt
            )
            answer = response.choices[0].message.content
            await interaction.followup.send(
                f"🔮 **{mode.title()} Tarot Reading** for {interaction.user.display_name}:\n\n{answer}"
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to get a reading: {e}")

async def setup(bot):
    await bot.add_cog(TarotWithMode(bot))

# This cog allows users to set their tarot reading mode and get readings based on that mode.
# It uses OpenAI's GPT-4 to generate tarot readings with different styles based on the user's choice.
# The modes are "standard" for serious readings and "meme" for humorous or chaotic readings.
# The user modes are stored in memory, but could be expanded to use a database or file for persistence.
# The tarot command generates a reading based on the selected mode and sends it as a response in the Discord channel.
# The setmode command allows users to change their tarot reading mode at any time.
# The cog is designed to be loaded into a Discord bot using the `setup` function.
# The tarot readings are generated with a system prompt that defines the role of the AI as either a professional tarot reader or a chaotic meme reader.
# The user is prompted to choose their mode before drawing a tarot card, and the reading is personalized with their username.
# The readings are formatted in a way that is suitable for Discord embeds, making them visually appealing and easy to read.
# The cog handles errors gracefully, providing feedback to the user if something goes wrong during the reading process.
# The use of OpenAI's API allows for dynamic and creative tarot readings that can                               adapt to user preferences.                                          