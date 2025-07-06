from datetime import datetime

# Background XP decay task and restricted /decayxp command integration
decay_support_code = '''
import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio

class XPDecayHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.decay_xp_background.start()

    def cog_unload(self):
        self.decay_xp_background.cancel()

    # Background task to decay XP every 24 hours
    @tasks.loop(hours=24)
    async def decay_xp_background(self):
        try:
            from bringus_xp import BringusXP
            xp_cog = self.bot.get_cog("BringusXP")
            if xp_cog:
                xp_cog.decay_all_xp()
                print(f"[XP Decay] Applied background XP decay at {datetime.now()}")
        except Exception as e:
            print(f"[XP Decay] Failed: {e}")

    # Optional manual command (Owner only)
    @app_commands.command(name="decayxp", description="Manually trigger XP decay (Owner only)")
    async def decayxp(self, interaction: discord.Interaction):
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("🚫 You are not authorized to use this command.", ephemeral=True)
            return

        try:
            from bringus_xp import BringusXP
            xp_cog = self.bot.get_cog("BringusXP")
            if xp_cog:
                xp_cog.decay_all_xp()
                await interaction.response.send_message("✅ XP decay manually triggered.")
            else:
                await interaction.response.send_message("⚠️ XP system not found.")
        except Exception as e:
            await interaction.response.send_message(f"❌ Decay failed: `{e}`")

async def setup(bot: commands.Bot):
    await bot.add_cog(XPDecayHandler(bot))
'''

with open("/mnt/data/xp_decay.py", "w") as f:
    f.write(decay_support_code)

"✅ XP decay background task and restricted `/decayxp` command written to `xp_decay.py`!"
