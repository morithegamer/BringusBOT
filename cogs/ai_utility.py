
import discord
from discord.ext import commands
from discord import app_commands
from utils.personality_router import get_persona_prompt
from utils.memory import load_memory, save_memory
import openai
import os
import random

openai.api_key = os.getenv("OPENAI_API_KEY")
user_memories = load_memory()

class AIUtility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tarot", description="Get a tarot reading (past, present, future)")
    async def tarot(self, interaction: discord.Interaction):
        await interaction.response.defer()
        system_prompt = get_persona_prompt("fluxy", "serious")
        user_prompt = (
            "Please perform a traditional 3-card tarot reading: Past, Present, and Future. "
            "Use themed descriptions and slight mysticism. Output in Markdown format."
        )
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            answer = response.choices[0].message.content
            await interaction.followup.send(f"🔮 **Tarot Reading**\n\n{answer}")
        except Exception as e:
            await interaction.followup.send(f"🃏 Tarot failed: `{e}`")

    @app_commands.command(name="summarize", description="Summarize a block of text")
    @app_commands.describe(text="Text to summarize")
    async def summarize(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer()
        system_prompt = get_persona_prompt("fluxy", "serious")
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Summarize the following text clearly and concisely:\n{text}"}
                ]
            )
            summary = response.choices[0].message.content
            await interaction.followup.send(f"📄 **Summary**:\n{summary}")
        except Exception as e:
            await interaction.followup.send(f"❌ Could not summarize: `{e}`")

    @app_commands.command(name="remember", description="Save a fact about yourself")
    @app_commands.describe(fact="What should I remember?")
    async def remember(self, interaction: discord.Interaction, fact: str):
        user_memories[interaction.user.id] = fact
        await interaction.response.send_message(f"🧠 Got it! I'll remember: `{fact}`", ephemeral=True)

    @app_commands.command(name="recall", description="Recall your saved fact")
    async def recall(self, interaction: discord.Interaction):
        fact = user_memories.get(interaction.user.id, None)
        if fact:
            await interaction.response.send_message(f"🔍 You told me: `{fact}`")
        else:
            await interaction.response.send_message("🤔 I don't remember anything you've told me yet.")

    @app_commands.command(name="rpfluxy", description="Start a Fluxy roleplay scene")
    @app_commands.describe(scene="Describe the scenario")
    async def rpfluxy(self, interaction: discord.Interaction, scene: str):
        await interaction.response.defer()
        system_prompt = get_persona_prompt("fluxy", "chaotic")
        prompt = f"Pretend you're roleplaying. Respond to this prompt: {scene}"
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            answer = response.choices[0].message.content
            await interaction.followup.send(f"🎭 **Fluxy RP Mode**:\n{answer}")
        except Exception as e:
            await interaction.followup.send(f"🎭 Roleplay error: `{e}`")

    @app_commands.command(name="captionimage", description="Upload an image to get a caption")
    async def captionimage(self, interaction: discord.Interaction, attachment: discord.Attachment):
        await interaction.response.defer()
        try:
            image_url = attachment.url
            system_prompt = get_persona_prompt("fluxy", "friendly")
            vision_response = openai.ChatCompletion.create(
                model="gpt-4-vision-preview",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe this image in a fun but helpful way."},
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }
                ],
                max_tokens=300
            )
            caption = vision_response.choices[0].message.content
            await interaction.followup.send(f"🖼️ **Fluxy sees:** {caption}")
        except Exception as e:
            await interaction.followup.send(f"⚠️ Couldn't process the image: `{e}`")

    @app_commands.command(name="fluxycustom", description="Use a custom system prompt with Fluxy")
    @app_commands.describe(system="Your custom persona prompt", question="Your question for Fluxy")
    async def fluxycustom(self, interaction: discord.Interaction, system: str, question: str):
        await interaction.response.defer()
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": question}
                ]
            )
            answer = response.choices[0].message.content
            await interaction.followup.send(f"💡 **Custom Fluxy says:**\n{answer}")
        except Exception as e:
            await interaction.followup.send(f"⚠️ Custom Fluxy failed: `{e}`")

async def setup(bot):
    await bot.add_cog(AIUtility(bot))
