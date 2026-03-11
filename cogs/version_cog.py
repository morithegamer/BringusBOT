import discord
from discord.ext import commands, tasks
from discord import app_commands
import platform
import sys
import time
import os
import psutil
import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
import subprocess
import pkg_resources
from typing import Optional

BOT_VERSION = "v9.7.8"
START_TIME = time.time()

class SystemView(discord.ui.View):
    """Interactive view for system information"""
    
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
    
    @discord.ui.button(label="💻 System Info", style=discord.ButtonStyle.primary)
    async def system_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog.create_system_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="📊 Performance", style=discord.ButtonStyle.secondary)
    async def performance_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog.create_performance_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🔧 Dependencies", style=discord.ButtonStyle.success)
    async def dependencies_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog.create_dependencies_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🌐 Network", style=discord.ButtonStyle.danger)
    async def network_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog.create_network_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

class VersionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.process = psutil.Process()
        self.boot_time = psutil.boot_time()
        self.startup_metrics = {
            "cpu_percent": 0.0,
            "memory_mb": 0.0,
            "startup_time": START_TIME
        }
        self._metrics_started = False
        
    async def cog_load(self):
        """Initialize background tasks when cog is loaded"""
        await self.start_background_tasks()
        
    async def start_background_tasks(self):
        """Start background tasks after bot is ready"""
        await self.bot.wait_until_ready()
        if not self._metrics_started:
            if not self.update_metrics_task.is_running():
                self.update_metrics_task.start()
            self._metrics_started = True
        
    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        if hasattr(self, 'update_metrics_task') and self.update_metrics_task.is_running():
            self.update_metrics_task.cancel()

    @tasks.loop(seconds=30)
    async def update_metrics_task(self):
        """Update system metrics periodically"""
        try:
            self.startup_metrics["cpu_percent"] = self.process.cpu_percent()
            self.startup_metrics["memory_mb"] = self.process.memory_info().rss / 1024 / 1024
        except Exception as e:
            print(f"Failed to update metrics: {e}")

    @update_metrics_task.before_loop
    async def before_update_metrics(self):
        await self.bot.wait_until_ready()

    def get_uptime(self) -> str:
        """Get formatted uptime string"""
        delta = int(time.time() - START_TIME)
        days, remainder = divmod(delta, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m {seconds}s"
        return f"{hours}h {minutes}m {seconds}s"

    def get_system_uptime(self) -> str:
        """Get system uptime"""
        uptime_seconds = time.time() - self.boot_time
        uptime_days = int(uptime_seconds // 86400)
        uptime_hours = int((uptime_seconds % 86400) // 3600)
        uptime_minutes = int((uptime_seconds % 3600) // 60)
        
        return f"{uptime_days}d {uptime_hours}h {uptime_minutes}m"

    def get_git_info(self) -> dict:
        """Get Git repository information"""
        try:
            commit_hash = subprocess.check_output(
                ['git', 'rev-parse', '--short', 'HEAD'], 
                stderr=subprocess.DEVNULL
            ).decode('utf-8').strip()
            
            commit_message = subprocess.check_output(
                ['git', 'log', '-1', '--pretty=%B'], 
                stderr=subprocess.DEVNULL
            ).decode('utf-8').strip()
            
            branch = subprocess.check_output(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'], 
                stderr=subprocess.DEVNULL
            ).decode('utf-8').strip()
            
            return {
                "hash": commit_hash,
                "message": commit_message[:50] + "..." if len(commit_message) > 50 else commit_message,
                "branch": branch
            }
        except:
            return {"hash": "Unknown", "message": "Git not available", "branch": "Unknown"}

    async def get_discord_status(self) -> dict:
        """Check Discord API status"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://discordstatus.com/api/v2/status.json", timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "status": data.get("status", {}).get("description", "Unknown"),
                            "indicator": data.get("status", {}).get("indicator", "unknown")
                        }
        except:
            pass
        return {"status": "Unable to fetch", "indicator": "unknown"}

    async def create_system_embed(self) -> discord.Embed:
        """Create detailed system information embed"""
        embed = discord.Embed(
            title="💻 Detailed System Information",
            color=discord.Color.blue()
        )
        
        # CPU Information
        cpu_count = psutil.cpu_count(logical=False)
        cpu_logical = psutil.cpu_count(logical=True)
        try:
            cpu_freq = psutil.cpu_freq()
            freq_text = f"{cpu_freq.current:.0f}MHz" if cpu_freq else "Unknown"
        except:
            freq_text = "Unknown"
            
        cpu_usage = psutil.cpu_percent(interval=1)
        
        embed.add_field(
            name="🖥️ CPU",
            value=f"Cores: {cpu_count} ({cpu_logical} logical)\n"
                  f"Frequency: {freq_text}\n"
                  f"Usage: {cpu_usage}%",
            inline=True
        )
        
        # Memory Information
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        embed.add_field(
            name="🧠 Memory",
            value=f"Total: {memory.total / 1024**3:.1f}GB\n"
                  f"Used: {memory.used / 1024**3:.1f}GB ({memory.percent}%)\n"
                  f"Swap: {swap.used / 1024**3:.1f}GB / {swap.total / 1024**3:.1f}GB",
            inline=True
        )
        
        # Disk Information
        try:
            disk_path = '/' if platform.system() != 'Windows' else 'C:\\'
            disk = psutil.disk_usage(disk_path)
            
            embed.add_field(
                name="💾 Disk",
                value=f"Total: {disk.total / 1024**3:.1f}GB\n"
                      f"Used: {disk.used / 1024**3:.1f}GB ({disk.used/disk.total*100:.1f}%)\n"
                      f"Free: {disk.free / 1024**3:.1f}GB",
                inline=True
            )
        except Exception as e:
            embed.add_field(
                name="💾 Disk",
                value="Unable to fetch disk info",
                inline=True
            )
        
        # OS Information
        embed.add_field(
            name="🖥️ Operating System",
            value=f"System: {platform.system()}\n"
                  f"Release: {platform.release()}\n"
                  f"Architecture: {platform.architecture()[0]}",
            inline=True
        )
        
        # System uptime
        embed.add_field(
            name="⏰ System Uptime",
            value=self.get_system_uptime(),
            inline=True
        )
        
        # Load average (Linux/Mac only)
        try:
            if platform.system() != 'Windows' and hasattr(os, 'getloadavg'):
                load_avg = getattr(os, 'getloadavg')()
                embed.add_field(
                    name="📊 Load Average",
                    value=f"1m: {load_avg[0]:.2f}\n5m: {load_avg[1]:.2f}\n15m: {load_avg[2]:.2f}",
                    inline=True
                )
        except:
            pass
        
        embed.set_footer(text="System metrics updated every 30 seconds")
        return embed

    async def create_performance_embed(self) -> discord.Embed:
        """Create performance metrics embed"""
        embed = discord.Embed(
            title="📊 Performance Metrics",
            color=discord.Color.green()
        )
        
        # Bot process information
        memory_info = self.process.memory_info()
        memory_percent = self.process.memory_percent()
        cpu_percent = self.process.cpu_percent()
        
        embed.add_field(
            name="🤖 Bot Process",
            value=f"CPU: {cpu_percent:.1f}%\n"
                  f"Memory: {memory_info.rss / 1024**2:.1f}MB ({memory_percent:.1f}%)\n"
                  f"Threads: {self.process.num_threads()}",
            inline=True
        )
        
        # Discord.py statistics
        embed.add_field(
            name="📡 Discord Stats",
            value=f"Guilds: {len(self.bot.guilds)}\n"
                  f"Users: {len(self.bot.users)}\n"
                  f"Channels: {len(list(self.bot.get_all_channels()))}",
            inline=True
        )
        
        # Latency information
        embed.add_field(
            name="🏓 Latency",
            value=f"WebSocket: {self.bot.latency*1000:.0f}ms\n"
                  f"Status: {'🟢 Good' if self.bot.latency < 0.2 else '🟡 Fair' if self.bot.latency < 0.5 else '🔴 Poor'}",
            inline=True
        )
        
        # Cog information
        loaded_cogs = len(self.bot.cogs)
        total_commands = len(self.bot.commands)
        slash_commands = len([cmd for cmd in self.bot.tree.walk_commands()])
        
        embed.add_field(
            name="🧩 Commands",
            value=f"Cogs: {loaded_cogs}\n"
                  f"Text Commands: {total_commands}\n"
                  f"Slash Commands: {slash_commands}",
            inline=True
        )
        
        # Event loop information
        loop = asyncio.get_event_loop()
        tasks = len(asyncio.all_tasks(loop))
        
        embed.add_field(
            name="🔄 Event Loop",
            value=f"Running Tasks: {tasks}\n"
                  f"Loop Running: {'✅' if loop.is_running() else '❌'}",
            inline=True
        )
        
        embed.add_field(
            name="⏱️ Uptime",
            value=f"Bot: {self.get_uptime()}\n"
                  f"Started: <t:{int(START_TIME)}:R>",
            inline=True
        )
        
        return embed

    async def create_dependencies_embed(self) -> discord.Embed:
        """Create dependencies information embed"""
        embed = discord.Embed(
            title="🔧 Dependencies & Versions",
            color=discord.Color.orange()
        )
        
        # Core dependencies
        dependencies = {
            "discord.py": discord.__version__,
            "Python": platform.python_version(),
            "aiohttp": "Unknown",
            "psutil": "Unknown",
            "asyncio": "Built-in"
        }
        
        # Get package versions safely
        for package in ["aiohttp", "psutil"]:
            try:
                version = pkg_resources.get_distribution(package).version
                dependencies[package] = version
            except:
                dependencies[package] = "Not installed"
        
        core_deps = "\n".join([f"{name}: `{version}`" for name, version in dependencies.items()])
        embed.add_field(name="📦 Core Dependencies", value=core_deps, inline=False)
        
        # Python information
        py_info = f"Implementation: {sys.implementation.name}\n"
        py_info += f"Compiler: {platform.python_compiler()}\n"
        py_info += f"Build: {platform.python_build()[0]}"
        
        embed.add_field(name="🐍 Python Details", value=py_info, inline=True)
        
        # Git information
        git_info = self.get_git_info()
        git_text = f"Branch: `{git_info['branch']}`\n"
        git_text += f"Commit: `{git_info['hash']}`\n"
        git_text += f"Message: {git_info['message']}"
        
        embed.add_field(name="📁 Git Info", value=git_text, inline=True)
        
        return embed

    async def create_network_embed(self) -> discord.Embed:
        """Create network information embed"""
        embed = discord.Embed(
            title="🌐 Network Information",
            color=discord.Color.red()
        )
        
        # Discord API status
        discord_status = await self.get_discord_status()
        status_emoji = {
            "none": "🟢",
            "minor": "🟡", 
            "major": "🔴",
            "critical": "⚫"
        }.get(discord_status["indicator"], "❓")
        
        embed.add_field(
            name="📡 Discord API",
            value=f"Status: {status_emoji} {discord_status['status']}\n"
                  f"Latency: {self.bot.latency*1000:.0f}ms",
            inline=True
        )
        
        # Network interfaces (if available)
        try:
            network_stats = psutil.net_io_counters()
            embed.add_field(
                name="📊 Network I/O",
                value=f"Sent: {network_stats.bytes_sent / 1024**2:.1f}MB\n"
                      f"Received: {network_stats.bytes_recv / 1024**2:.1f}MB\n"
                      f"Packets Sent: {network_stats.packets_sent:,}",
                inline=True
            )
        except:
            embed.add_field(
                name="📊 Network I/O",
                value="Unable to fetch network stats",
                inline=True
            )
        
        # Connection info
        try:
            connections = len(psutil.net_connections())
            embed.add_field(
                name="🔗 Connections",
                value=f"Active: {connections}",
                inline=True
            )
        except:
            embed.add_field(
                name="🔗 Connections",
                value="Unable to fetch connection info",
                inline=True
            )
        
        return embed

    @app_commands.command(name="version", description="Display version and system details.")
    async def version(self, interaction: discord.Interaction):
        uptime = self.get_uptime()
        total_cogs = len(self.bot.cogs)
        py_ver = platform.python_version()
        dpy_ver = discord.__version__
        dockerized = os.path.exists("/.dockerenv")
        
        embed = discord.Embed(
            title="🛠️ Bringus Bot Status",
            description="Here's everything under the hood. 💙",
            color=discord.Color.blurple()
        )
        
        # Basic info
        embed.add_field(name="🧪 Version", value=f"`{BOT_VERSION}`", inline=True)
        embed.add_field(name="📦 Python", value=f"`{py_ver}`", inline=True)
        embed.add_field(name="🔧 discord.py", value=f"`{dpy_ver}`", inline=True)
        
        # Performance
        embed.add_field(name="⏱️ Uptime", value=uptime, inline=False)
        embed.add_field(name="🧩 Cogs Loaded", value=f"`{total_cogs}`", inline=True)
        embed.add_field(name="🏓 Latency", value=f"`{self.bot.latency*1000:.0f}ms`", inline=True)
        embed.add_field(name="🐳 Docker", value="Yes 🐳" if dockerized else "Nope", inline=True)

        # System info
        embed.add_field(name="🔹 Python Path", value=f"`{sys.executable}`", inline=False)
        embed.add_field(name="🧠 Memory Usage", value=f"`{self.startup_metrics['memory_mb']:.1f}MB`", inline=True)
        embed.add_field(name="🖥️ CPU Usage", value=f"`{self.startup_metrics['cpu_percent']:.1f}%`", inline=True)
        embed.add_field(name="💻 Platform", value=f"`{sys.platform}`", inline=True)
        
        # Git info
        git_info = self.get_git_info()
        embed.add_field(name="📁 Git Commit", value=f"`{git_info['hash']}`", inline=True)
        embed.add_field(name="🌿 Branch", value=f"`{git_info['branch']}`", inline=True)
        
        # Timestamps
        embed.add_field(name="📅 Boot Time", value=f"<t:{int(START_TIME)}:F>", inline=False)
        embed.add_field(name="🔄 Last Restart", value=f"<t:{int(START_TIME)}:R>", inline=False)
        
        # Visual elements
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/555148516708712481/1392856866262089768/LYNL8FC.jpg?ex=6892acca&is=68915b4a&hm=8dd2f9c9d94df8c18e3d1497fb6b6a6a323b3be0a2c3905d7d36de9061ab8b9b&")
        if self.bot.user:
            embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Made with 💙 by Mori | WebFlux Labs")
        embed.timestamp = discord.utils.utcnow()
        
        # Interactive view
        view = SystemView(self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="sysinfo", description="Detailed system information")
    async def sysinfo(self, interaction: discord.Interaction):
        """Show detailed system information"""
        embed = await self.create_system_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="performance", description="Show bot performance metrics")
    async def performance(self, interaction: discord.Interaction):
        """Show performance metrics"""
        embed = await self.create_performance_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="ping", description="Check bot latency")
    async def ping(self, ctx):
        """Simple ping command with detailed latency info"""
        start_time = time.time()
        
        embed = discord.Embed(title="🏓 Pong!", color=discord.Color.green())
        
        # WebSocket latency
        ws_latency = self.bot.latency * 1000
        
        # Calculate message latency
        message = await ctx.send(embed=embed)
        end_time = time.time()
        message_latency = (end_time - start_time) * 1000
        
        # Update embed with latency info
        embed.add_field(name="📡 WebSocket", value=f"{ws_latency:.0f}ms", inline=True)
        embed.add_field(name="💬 Message", value=f"{message_latency:.0f}ms", inline=True)
        embed.add_field(name="🤖 API", value=f"{(ws_latency + message_latency)/2:.0f}ms", inline=True)
        
        # Status indicators
        if ws_latency < 100:
            embed.color = discord.Color.green()
            status = "🟢 Excellent"
        elif ws_latency < 200:
            embed.color = discord.Color.yellow()
            status = "🟡 Good"
        else:
            embed.color = discord.Color.red()
            status = "🔴 Poor"
        
        embed.add_field(name="📊 Status", value=status, inline=False)
        
        await message.edit(embed=embed)

    @commands.hybrid_command(name="uptime", description="Show detailed uptime information")
    async def uptime(self, ctx):
        """Show detailed uptime information"""
        embed = discord.Embed(
            title="⏰ Uptime Information",
            color=discord.Color.blue()
        )
        
        bot_uptime = self.get_uptime()
        system_uptime = self.get_system_uptime()
        
        embed.add_field(name="🤖 Bot Uptime", value=bot_uptime, inline=True)
        embed.add_field(name="🖥️ System Uptime", value=system_uptime, inline=True)
        embed.add_field(name="📅 Started", value=f"<t:{int(START_TIME)}:F>", inline=False)
        embed.add_field(name="🔄 Relative", value=f"<t:{int(START_TIME)}:R>", inline=True)
        
        # Uptime percentage (last 30 days)
        days_running = (time.time() - START_TIME) / 86400
        uptime_percent = min(100.0, (days_running / 30) * 100) if days_running > 0 else 100.0
        embed.add_field(name="📊 Uptime %", value=f"{uptime_percent:.2f}%", inline=True)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(VersionCog(bot))
