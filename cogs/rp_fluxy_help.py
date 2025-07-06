import discord
from discord.ext import commands
from discord import app_commands
from utils.chatgpt import ask_chatgpt

class RPAndHelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rpbringus", description="Roleplay with Jon (Bringus) in character!")
    @app_commands.describe(scene="What's the roleplay scenario?")
    async def rpbringus(self, interaction: discord.Interaction, scene: str):
        await interaction.response.defer(thinking=True)
        try:
            system_prompt = (
                "You are Jon (Bringus), a chaotic but clever digital fox. "
                "You love roleplaying wildly, unpredictably, and with a flair for dramatic fun."
            )
            user_prompt = f"Begin roleplaying with the user based on this scene:\n{scene}"
            reply = await ask_chatgpt(user_prompt, system_prompt)
            embed = discord.Embed(
                title="🎭 Jon (Bringus) Roleplay",
                description=reply,
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"🧨 Roleplay error: `{e}`")

    @app_commands.command(name="fluxyhelp", description="Show help for Fluxy's AI features")
    async def fluxyhelp(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="💫 Fluxy Help – AI Commands",
            description="Here's everything Fluxy can do for you!",
            color=discord.Color.from_str("#ED74F5")
        )
        embed.add_field(name="/ask", value="Ask Fluxy any question based on her current mood.", inline=False)
        embed.add_field(name="/fluxymood", value="Change how Fluxy responds to you. (Friendly, Sassy, Serious, Chaotic)", inline=False)
        embed.add_field(name="/fluxycustom", value="Use a completely custom persona system prompt!", inline=False)
        embed.add_field(name="/tarot", value="Fluxy gives a traditional 3-card tarot reading.", inline=False)
        embed.add_field(name="/summarize", value="Summarize any block of text with AI.", inline=False)
        embed.add_field(name="/captionimage", value="Upload an image and Fluxy will describe it using Vision AI.", inline=False)
        embed.add_field(name="/remember & /recall", value="Save something for Fluxy to remember and ask her later.", inline=False)
        embed.add_field(name="/rpfluxy", value="Roleplay a wild scenario with Fluxy.", inline=False)
        embed.set_footer(text="Powered by Fluxy 💙 GPT-4")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="bringushelp", description="Show help for core BringusBOT features")
    async def bringushelp(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛠️ BringusBOT Help Menu",
            description="Main commands available in your server!",
            color=discord.Color.from_str("#39A2F5")
        )
        embed.add_field(name="🎮 Fun", value="/count, /meme, /rpbringus", inline=False)
        embed.add_field(name="📊 XP & Rank", value="/rank, /verify", inline=False)
        embed.add_field(name="🎭 Personality", value="/askbringus, /ask, /fluxymood, /tarot", inline=False)
        embed.add_field(name="📌 Utility", value="/reactionrole, /ping", inline=False)
        embed.set_footer(text="BringusBOT – Private AI Assistant for your server only 💙")

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(RPAndHelp(bot))