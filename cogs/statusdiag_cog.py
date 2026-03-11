import discord
from discord.ext import commands
from discord import app_commands
import platform
import os
import time
import psutil
from utils import debuglog

BOOT_TIME = time.time()

class StatusDiag(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="uptime", description="Check how long the bot has been running.")
    async def uptime(self, interaction: discord.Interaction):
        delta = time.time() - BOOT_TIME
        hours, rem = divmod(delta, 3600)
        minutes, seconds = divmod(rem, 60)
        msg = f"🕒 Uptime: {int(hours)}h {int(minutes)}m {int(seconds)}s"
        await interaction.response.send_message(msg)

    @app_commands.command(name="latency", description="Check Discord API latency.")
    async def latency(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000, 2)
        await interaction.response.send_message(f"📡 Discord latency: `{latency_ms}ms`")

    @app_commands.command(name="systemcheck", description="Show system info and access status.")
    async def systemcheck(self, interaction: discord.Interaction):
        uname = platform.uname()
        pyv = platform.python_version()
        os_name = uname.system
        try:
            sudo = getattr(os, 'geteuid', lambda: -1)() == 0
        except (AttributeError, OSError):
            sudo = "N/A"
        dockerized = os.path.exists("/.dockerenv")
        mem = psutil.virtual_memory()
        msg = (
            f"🖥️ **System**: {os_name} {uname.release}\\n"
            f"🐍 **Python**: {pyv}\\n"
            f"📦 **Dockerized**: `{dockerized}`\\n"
            f"🧰 **Root/Sudo**: `{sudo}`\\n"
            f"💾 **Memory**: {round(mem.used / 1024**2)} MB / {round(mem.total / 1024**2)} MB"
        )
        await interaction.response.send_message(msg)

    @app_commands.command(name="loghealth", description="Check debug log write permissions.")
    async def loghealth(self, interaction: discord.Interaction):
        try:
            test = debuglog.log("HEALTH", "Testing log health", level="DEBUG")
            await interaction.response.send_message(f"✅ Log test succeeded: `{test}`")
        except Exception as e:
            await interaction.response.send_message(f"❌ Log failed: `{e}`")

    @app_commands.command(name="botdiag", description="Run a full bot diagnostic.")
    async def botdiag(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000, 2)
        delta = time.time() - BOOT_TIME
        hours, rem = divmod(delta, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
        dockerized = os.path.exists("/.dockerenv")
        try:
            sudo = getattr(os, 'geteuid', lambda: -1)() == 0
        except (AttributeError, OSError):
            sudo = "N/A"

        embed = discord.Embed(title="🧠 Bringus System Diagnostic", color=0x00FFFF)
        embed.add_field(name="Uptime", value=uptime_str)
        embed.add_field(name="Latency", value=f"{latency_ms}ms")
        embed.add_field(name="Dockerized", value=str(dockerized))
        embed.add_field(name="Root Access", value=str(sudo))
        embed.add_field(name="Python", value=platform.python_version())
        embed.set_footer(text="🦊 Bringus Diagnostic System")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="diskstatus", description="Show disk usage and availability.")
    async def diskstatus(self, interaction: discord.Interaction):
        usage = psutil.disk_usage("/")
        total = round(usage.total / 1024**3, 2)
        used = round(usage.used / 1024**3, 2)
        free = round(usage.free / 1024**3, 2)
        percent = usage.percent
        await interaction.response.send_message(
            f"💽 **Disk Usage**: {used}GB / {total}GB ({percent}%)\\n🟢 Free: {free}GB"
        )

    @app_commands.command(name="envdump", description="Display safe environment variable dump.")
    async def envdump(self, interaction: discord.Interaction):
        envs = os.environ
        redacted_keys = ["TOKEN", "KEY", "SECRET", "PASSWORD"]
        safe_envs = [
            f"`{k}`: `{v if not any(key in k.upper() for key in redacted_keys) else '[REDACTED]'}`"
            for k, v in envs.items() if len(k) < 40
        ]
        chunks = "\\n".join(safe_envs[:25])  # limit to 25 vars
        await interaction.response.send_message(f"📦 **Environment Variables (Safe Dump)**:\\n{chunks}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(StatusDiag(bot))