# FREE6 Verification System
from discord.ext import commands
import discord
from discord import app_commands

class BringusVerify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="verify", description="Start your After Hours Verification.")
    async def verify(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔍 Let's begin your verification. Please answer the following questions.", ephemeral=True)

        def check(m):
            return m.author.id == interaction.user.id and m.channel == interaction.channel

        await interaction.followup.send("1️⃣ What is your age?")
        try:
            age_msg = await self.bot.wait_for('message', check=check, timeout=120)
        except:
            await interaction.followup.send("⏳ Verification timed out.", ephemeral=True)
            return

        try:
            age = int(age_msg.content)
            if age < 18:
                await interaction.followup.send("❌ You must be 18+ to access After Hours.", ephemeral=True)
                return
        except ValueError:
            await interaction.followup.send("❌ Invalid input. Verification cancelled.", ephemeral=True)
            return

        await interaction.followup.send("2️⃣ Do you consent to mature discussions? (yes/no)")
        try:
            consent_msg = await self.bot.wait_for('message', check=check, timeout=120)
        except:
            await interaction.followup.send("⏳ Verification timed out.", ephemeral=True)
            return

        consent = consent_msg.content.lower()
        if consent not in ["yes", "y"]:
            await interaction.followup.send("❌ Consent not given. Verification cancelled.", ephemeral=True)
            return

        role = discord.utils.get(interaction.guild.roles, name="After Hours")
        if role:
            await interaction.user.add_roles(role)
            await interaction.followup.send("✅ Verification complete! Welcome to the After Hours.", ephemeral=True)

            log_channel = discord.utils.get(interaction.guild.text_channels, name="verified-logs")
            if log_channel:
                await log_channel.send(f"✅ {interaction.user.mention} verified for After Hours access!")
        else:
            await interaction.followup.send("⚠️ 'After Hours' role not found. Please contact staff.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(BringusVerify(bot))