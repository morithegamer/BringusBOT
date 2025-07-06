# Velvet Room Verification System (NSFW After Hours)
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

        if user_id in self.cooldowns:
            elapsed = (now - self.cooldowns[user_id]).total_seconds()
            if elapsed < 60:
                await interaction.response.send_message("⏳ Please wait before trying to verify again.", ephemeral=True)
                return

        self.cooldowns[user_id] = now

        await interaction.response.send_message("🔍 Let's begin your verification. Please answer the following:", ephemeral=True)

        try:
            # Age Check
            await interaction.channel.typing()
            await asyncio.sleep(1)
            await interaction.followup.send("1️⃣ What is your age?", ephemeral=True)
            age_msg = await interaction.client.wait_for('message', check=lambda m: m.author.id == user_id, timeout=120)

            try:
                age = int(age_msg.content)
            except ValueError:
                await interaction.followup.send("❌ Invalid age format. Please enter a number.", ephemeral=True)
                return

            if age < 18:
                await interaction.followup.send("❌ You must be 18+ to access After Hours.", ephemeral=True)
                return

            # Consent Check
            await interaction.channel.typing()
            await asyncio.sleep(1)
            await interaction.followup.send("2️⃣ Do you consent to mature discussions? (yes/no)", ephemeral=True)
            consent_msg = await interaction.client.wait_for('message', check=lambda m: m.author.id == user_id, timeout=120)

            consent = consent_msg.content.lower()
            if consent not in ["yes", "y"]:
                await interaction.followup.send("❌ Consent not given. Verification cancelled.", ephemeral=True)
                return

            # Grant Role
            role = discord.utils.get(interaction.guild.roles, id=715933446790185062)
            if role:
                await interaction.user.add_roles(role)
                await interaction.followup.send("✅ Verification complete! Welcome to the After Hours.", ephemeral=True)

                log_channel = discord.utils.get(interaction.guild.text_channels, id=1365925137467183124)
                if log_channel:
                    await log_channel.send(f"✅ {interaction.user.mention} has verified for After Hours access.")
            else:
                await interaction.followup.send("⚠️ 'After Hours' role not found. Please contact staff.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send("❌ Verification failed or timed out.", ephemeral=True)
            print(f"[Bringus] Verification Error: {e}")

class BringusVerify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(1366264816855027782)  # Your verification channel ID
        if channel:
            embed = discord.Embed(
                title="🎴 Welcome to the Velvet Room: After Hours",
                description="Step forward if you wish to cross into the After Hours. Verification ensures safety and respect within these walls.",
                color=0x1F1E33
            )
            embed.set_footer(text="Your journey into the After Hours begins here. 🎴")
            embed.set_image(url="https://i.imgur.com/8sfRdbP.jpeg")  # Velvet Room image

            await channel.purge(limit=10)
            await channel.send(embed=embed, view=VerifyView())

async def setup(bot: commands.Bot):
    await bot.add_cog(BringusVerify(bot))
