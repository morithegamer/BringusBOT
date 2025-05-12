import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime

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
            await interaction.followup.send("1️⃣ Please enter your Date of Birth (MM/DD/YYYY):", ephemeral=True)
            dob_msg = await interaction.client.wait_for('message', check=lambda m: m.author.id == user_id, timeout=120)
            dob_str = dob_msg.content.strip()
            await dob_msg.delete()

            try:
                dob = datetime.strptime(dob_str, "%m/%d/%Y")
                age = (datetime.utcnow() - dob).days // 365
            except ValueError:
                await interaction.followup.send("❌ Invalid date format. Please use MM/DD/YYYY.", ephemeral=True)
                return

            if age < 18:
                await interaction.followup.send("❌ You must be 18+ to access After Hours.", ephemeral=True)
                return

            await interaction.channel.typing()
            await asyncio.sleep(1)
            await interaction.followup.send("✅ Verified! Welcome to After Hours.", ephemeral=True)

            role = discord.utils.get(interaction.guild.roles, id=715933446790185062)
            if role:
                await interaction.user.add_roles(role)
                log_channel = discord.utils.get(interaction.guild.text_channels, id=1365925137467183124)
                if log_channel:
                    await log_channel.send(f"✅ {interaction.user.mention} has verified with DOB: {dob_str}.")
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
            file = discord.File("image.png", filename="image.png")
            embed.set_image(url="attachment://image.png")
            await channel.purge(limit=10)
            await channel.send(embed=embed, view=VerifyView(), file=file)

async def setup(bot):
    await bot.add_cog(BringusVerify(bot))
