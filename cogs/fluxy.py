import discord
from discord import app_commands
from discord.ext import commands
from utils.db import save_user_mood, get_user_mood
from utils.personality_router import get_persona_prompt
from utils.memory import update_memory, get_memory, clear_memory
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MOOD_PRESETS = ["friendly", "sassy", "serious", "chaotic", "shy", "flirty", "deadpan"]
user_moods = {}

# Toggle flag for enabling/disabling OpenAI replies
OPENAI_ENABLED = True  # Can be toggled later

class FluxyPersona(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setfluxymood", description="Set Fluxy's personality mood.")
    @app_commands.describe(mood="Select a personality preset for Fluxy.")
    @app_commands.choices(mood=[discord.app_commands.Choice(name=m.title(), value=m) for m in MOOD_PRESETS])
    async def setfluxymoods(self, interaction: discord.Interaction, mood: str):
        save_user_mood(interaction.user.id, mood)
        await interaction.response.send_message(
            f"🎀 Fluxy's mood is now set to **{mood.title()}** for you!",
            ephemeral=True
        )

    @app_commands.command(name="clearmemory", description="Clear your memory with Fluxy.")
    async def clearmemory(self, interaction: discord.Interaction):
        clear_memory(interaction.user.id)
        await interaction.response.send_message("🧠 Your memory with Fluxy has been cleared.", ephemeral=True)

    @app_commands.command(name="mystory", description="See what Fluxy remembers about you!")
    async def mystory(self, interaction: discord.Interaction):
        memory = get_memory(interaction.user.id)
        if memory:
            story = "\n".join(memory[-10:])
            await interaction.response.send_message(f"🧠 Here's a peek at your story with Fluxy:\n```{story}```", ephemeral=True)
        else:
            await interaction.response.send_message("🧠 I don't remember anything about you yet!", ephemeral=True)

    @app_commands.command(name="ask", description="Ask Fluxy a question!")
    @app_commands.describe(question="What would you like to ask Fluxy?")
    async def ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer(thinking=True)

        if not OPENAI_ENABLED:
            await interaction.followup.send("⚠️ Fluxy's AI brain is currently offline. Try again later.")
            return

        mood = get_user_mood(interaction.user.id, "friendly")
        system_prompt = get_persona_prompt("fluxy", mood)

        try:
            past_mem = "\n".join(get_memory(interaction.user.id))
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{past_mem}\n{question}"}
                ]
            )
            answer = response.choices[0].message.content or "🤖 (No content returned.)"

            update_memory(interaction.user.id, f"User: {question}")
            update_memory(interaction.user.id, f"Assistant: {answer}")

            embed = discord.Embed(
                title=f"🎀 Fluxy ({mood.title()} Mode) says:",
                description=answer[:1800],
                color=discord.Color.from_str("#BC51D2")
            )
            embed.set_footer(text=f"Mood: {mood.title()} | Powered by GPT-4o • Fluxy Bot 💬")
            embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/555148516708712481/1392857212321271818/1tOgqlb.jpg")

            await interaction.followup.send(embed=embed)
            msg = await interaction.followup.send(content="\u200e", embed=embed)

            if isinstance(msg, discord.Message):
                msg.create_thread(
                    name=f"{interaction.user.display_name} x Fluxy 💬",
                    auto_archive_duration=60
                )
                await interaction.followup.send(
                    f"🧵 A thread has been created for your conversation with Fluxy: {msg.jump_url}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("⚠️ Fluxy couldn't create a thread for some reason. Please try again later.")

        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Fluxy couldn't respond: `{e}`")
        except Exception as e:
            await interaction.followup.send(f"⚠️ Fluxy had a hiccup: `{e}`")

async def setup(bot: commands.Bot):
    await bot.add_cog(FluxyPersona(bot))
