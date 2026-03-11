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
        # Start via DM (no personal documents or IDs collected)
        try:
            member: discord.Member = interaction.user if isinstance(interaction.user, discord.Member) else await interaction.guild.fetch_member(user_id)
            dm = await member.create_dm()
            await interaction.response.send_message("📨 Check your DMs to continue verification. If you didn't receive a DM, enable DMs from server members.", ephemeral=True)

            await dm.send("🔍 Let's begin your verification in private.")
            await dm.send("⚠️ For your safety: Never share photos of your government ID or any personal documents. We will never ask for them.")
            await dm.send("1️⃣ Are you 18 or older? (yes/no)")

            def dm_check(m: discord.Message):
                return m.author.id == user_id and isinstance(m.channel, discord.DMChannel)

            age_confirm_msg = await interaction.client.wait_for('message', check=dm_check, timeout=180)
            age_confirm = age_confirm_msg.content.lower().strip()
            if age_confirm not in ("yes", "y"):
                await dm.send("❌ You must self-confirm that you're 18 or older to access After Hours.")
                return

            await dm.send("2️⃣ Do you consent to mature discussions? (yes/no)")
            consent_msg = await interaction.client.wait_for('message', check=dm_check, timeout=180)
            consent = consent_msg.content.lower().strip()
            if consent not in ("yes", "y"): 
                await dm.send("❌ Consent not given. Verification cancelled.")
                return

            if interaction.guild is None:
                await dm.send("❌ Guild context not found. Please click the button inside a server next time.")
                return

            # Grant After Hours role if exists
            role = discord.utils.get(interaction.guild.roles, id=715933446790185062)
            if role:
                try:
                    await member.add_roles(role, reason="After Hours verification passed")
                except Exception:
                    pass

            # Confirm via DM and log to staff channel (no IDs collected)
            await dm.send("✅ Thanks! You've been granted After Hours access based on your self-attestation.")
            log_channel = discord.utils.get(interaction.guild.text_channels, id=1365925137467183124)
            if log_channel:
                await log_channel.send(f"✅ {member.mention} self-verified as 18+ and consented to mature discussions. Role granted.")

        except asyncio.TimeoutError:
            try:
                await interaction.followup.send("⌛ Verification timed out. Please try again.", ephemeral=True)
            except Exception:
                pass
        except discord.Forbidden:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ I couldn't DM you. Please enable DMs from server members and try again.", ephemeral=True)
            else:
                await interaction.followup.send("❌ I couldn't DM you. Please enable DMs from server members and try again.", ephemeral=True)
        except Exception as e:
            try:
                await interaction.followup.send("❌ Verification failed due to an error.", ephemeral=True)
            except Exception:
                pass
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
            embed.set_image(url="https://cdn.discordapp.com/attachments/555148516708712481/1393061165575180450/YwpUa1n.jpg?ex=6871cccf&is=68707b4f&hm=55af258e00b7eda2ee4b7d41c3c84e9de10785c56c5ce9f178b9195dc63cf81a&")

            await channel.purge(limit=10)
            await channel.send(embed=embed, view=VerifyView())

async def setup(bot: commands.Bot):
    await bot.add_cog(BringusVerify(bot))
