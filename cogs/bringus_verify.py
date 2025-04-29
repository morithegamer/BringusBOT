
import discord
from discord.ext import commands
from discord import app_commands
import asyncio

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.cooldowns = {}

    @discord.ui.button(label="✅ Begin Verification", style=discord.ButtonStyle.success, custom_id="verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        now = discord.utils.utcnow()
        if user_id in self.cooldowns and (now - self.cooldowns[user_id]).total_seconds() < 60:
            await interaction.response.send_message("⏳ Wait before verifying again.", ephemeral=True)
            return

        self.cooldowns[user_id] = now
        await interaction.response.send_message("🔍 Let's begin verification!", ephemeral=True)

        try:
            await interaction.channel.typing()
            await asyncio.sleep(1)
            await interaction.followup.send("1️⃣ What is your age?", ephemeral=True)
            age_msg = await interaction.client.wait_for('message', check=lambda m: m.author.id == user_id, timeout=120)
            age = int(age_msg.content)
            await age_msg.delete()

            if age < 18:
                await interaction.followup.send("❌ You must be 18+ to access After Hours.", ephemeral=True)
                return

            await interaction.channel.typing()
            await asyncio.sleep(1)
            await interaction.followup.send("2️⃣ Do you consent to mature discussions? (yes/no)", ephemeral=True)
            consent_msg = await interaction.client.wait_for('message', check=lambda m: m.author.id == user_id, timeout=120)
            consent = consent_msg.content.lower()
            await consent_msg.delete()

            if consent not in ["yes", "y"]:
                await interaction.followup.send("❌ Consent not given.", ephemeral=True)
                return

            role = discord.utils.get(interaction.guild.roles, id=715933446790185062)
            if role:
                await interaction.user.add_roles(role)
                await interaction.followup.send("✅ Verified! Welcome to After Hours.", ephemeral=True)
                log_channel = discord.utils.get(interaction.guild.text_channels, id=1365925137467183124)
                if log_channel:
                    await log_channel.send(f"✅ {interaction.user.mention} has verified.")
            else:
                await interaction.followup.send("⚠️ 'After Hours' role not found.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send("❌ Verification failed or timed out.", ephemeral=True)
            print(e)

class BringusVerify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(1366264816855027782)
        if channel:
            embed = discord.Embed(
                title="🎴 Velvet Room: After Hours Verification",
                description="Step forward if you wish to cross into After Hours.",
                color=0x1F1E33
            )
            embed.set_image(url="https://i.imgur.com/qYjzKyy.png")
            await channel.purge(limit=10)
            await channel.send(embed=embed, view=VerifyView())

async def setup(bot):
    await bot.add_cog(BringusVerify(bot))
