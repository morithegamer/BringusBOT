import discord
from discord.ext import commands, tasks
from discord import app_commands
from utils.db import init_db, purge_old_data
from utils.personality_router import get_persona_prompt, list_available_personalities
import asyncio
import os
import random
import logging
import time
import json
import signal
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────────────────────
# Configuration & Setup
# ─────────────────────────────────────────────────────────────────────────────

load_dotenv()

# Configure enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bringusbot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('BringusBot')

# Set debug logging for startup issues
startup_logger = logging.getLogger('BringusBot.Startup')
startup_logger.setLevel(logging.DEBUG)

# Environment variables with validation
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PREFIX = os.getenv("PREFIX", "!")
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
PUBLIC_WEBHOOK = os.getenv("PUBLIC_WEBHOOK")
STAFF_WEBHOOK = os.getenv("STAFF_WEBHOOK")
GUILD_ID = os.getenv("GUILD_ID")
# Use env override for version; fallback to latest
BOT_VERSION = os.getenv("BOT_VERSION", "v9.7.5")

if not DISCORD_TOKEN:
    logger.critical("DISCORD_TOKEN not found in environment variables!")
    sys.exit(1)

# Enhanced intents setup (updated for newer discord.py)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
intents.messages = True        # replaces guild_messages/dm_messages
intents.reactions = True       # replaces guild_reactions/dm_reactions
intents.guilds = True
intents.guild_scheduled_events = True
intents.typing = False  # Disable typing events for performance

# ─────────────────────────────────────────────────────────────────────────────
# Enhanced Bot Class
# ─────────────────────────────────────────────────────────────────────────────

class BringusBot(commands.Bot):
    def __init__(self):
        startup_logger.info("🔧 Initializing BringusBot...")
        
        super().__init__(
            command_prefix=commands.when_mentioned_or(PREFIX),
            intents=intents,
            case_insensitive=True,
            strip_after_prefix=True,
            help_command=None
        )
        
        # Bot statistics
        self.start_time = time.time()
        self.commands_used = 0
        self.messages_seen = 0
        self.errors_count = 0
        self.uptime_data = {
            "total_restarts": 0,
            "last_restart": datetime.now(timezone.utc).isoformat(),
            "crash_log": []
        }
        
        # Status management
        self.status_options = [
            (discord.Status.online, discord.Game("Counting memes! 🤖")),
            (discord.Status.idle, discord.Activity(type=discord.ActivityType.watching, name="Velvet Room visitors 💎")),
            (discord.Status.dnd, discord.Activity(type=discord.ActivityType.listening, name="whispers of memers ✨")),
            (discord.Status.idle, discord.Activity(type=discord.ActivityType.playing, name="with furry art 🎨")),
            (discord.Status.online, discord.Activity(type=discord.ActivityType.watching, name="Discord for drama 👀")),
            (discord.Status.dnd, discord.Game("Hide and Seek with bugs 🐛"))
        ]
        
        # Cog management
        self.loaded_cogs = set()
        self.failed_cogs = {}
        
        # Startup control
        self._ready_event = asyncio.Event()
        self._startup_complete = False
        
        startup_logger.info("✅ BringusBot initialization complete")

    def load_uptime_data(self):
        """Load uptime data from file - NON-BLOCKING"""
        try:
            startup_logger.debug("📊 Loading uptime data...")
            if os.path.exists('uptime_data.json'):
                with open('uptime_data.json', 'r') as f:
                    self.uptime_data.update(json.load(f))
                self.uptime_data["total_restarts"] += 1
            startup_logger.debug("✅ Uptime data loaded")
        except Exception as e:
            startup_logger.warning(f"⚠️ Failed to load uptime data: {e}")

    def save_uptime_data(self):
        """Save uptime data to file"""
        try:
            self.uptime_data["last_restart"] = datetime.now(timezone.utc).isoformat()
            with open('uptime_data.json', 'w') as f:
                json.dump(self.uptime_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save uptime data: {e}")

    async def setup_hook(self) -> None:
        """Called when bot is starting up - CRITICAL PATH"""
        startup_logger.info(f"🚀 BringusBot {BOT_VERSION} setup_hook starting...")
        
        # Load uptime data (non-blocking)
        self.load_uptime_data()
        
        # Initialize database with timeout
        try:
            startup_logger.info("🗄️ Initializing database...")
            # Import here to avoid blocking main thread
            from utils.db import init_db
            
            # Run with timeout to prevent hanging
            await asyncio.wait_for(
                asyncio.to_thread(init_db),
                timeout=10.0
            )
            startup_logger.info("✅ Database initialized successfully")
        except asyncio.TimeoutError:
            startup_logger.error("❌ Database initialization timed out after 10s")
        except Exception as e:
            startup_logger.error(f"❌ Database initialization failed: {e}")
        
        # Load cogs with enhanced logging
        await self.load_all_cogs()
        
        # DON'T start background tasks here - wait for on_ready
        startup_logger.info("✅ setup_hook completed successfully")

    async def on_ready(self):
        """Called when bot is ready - with watchdog timeout"""
        startup_logger.info("🎯 on_ready() event triggered")
        
        # Create watchdog task
        watchdog_task = asyncio.create_task(self._ready_watchdog())
        
        try:
            await asyncio.wait_for(self._on_ready_impl(), timeout=30.0)
            watchdog_task.cancel()
            self._startup_complete = True
            self._ready_event.set()
            startup_logger.info("🎉 BringusBot is fully ready!")
        except asyncio.TimeoutError:
            startup_logger.error("❌ on_ready() timed out after 30 seconds!")
            watchdog_task.cancel()
        except Exception as e:
            startup_logger.error(f"❌ on_ready() failed: {e}", exc_info=True)
            watchdog_task.cancel()

    async def _ready_watchdog(self):
        """Watchdog to detect if on_ready hangs"""
        await asyncio.sleep(30)
        if not self._startup_complete:
            startup_logger.error("🚨 WATCHDOG: on_ready() has been running for 30+ seconds!")
            startup_logger.error("🚨 Bot may be frozen during startup")

    async def _on_ready_impl(self):
        """Actual on_ready implementation"""
        startup_logger.info("📊 Gathering bot information...")
        
        if self.user:
            logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        else:
            logger.warning("Bot user is None during on_ready event")
        
        logger.info(f"Connected to {len(self.guilds)} guilds")
        logger.info(f"Serving {len(set(self.get_all_members()))} users")
        
        # Set initial status
        startup_logger.info("🎭 Setting initial status...")
        await self.change_status()
        
        # Sync slash commands with timeout
        startup_logger.info("🔄 Syncing slash commands...")
        await asyncio.wait_for(self.sync_commands(), timeout=15.0)
        
        # Start background tasks AFTER bot is ready
        startup_logger.info("⚙️ Starting background tasks...")
        if not self.periodic_tasks.is_running():
            self.periodic_tasks.start()
        if not self.status_rotation.is_running():
            self.status_rotation.start()
        
        # Send startup notification
        startup_logger.info("📡 Sending startup notification...")
        await self.send_startup_notification()

    async def on_message(self, message):
        """Enhanced message handling"""
        if message.author.bot:
            return
        
        self.messages_seen += 1
        await self.process_commands(message)

    async def on_command(self, ctx):
        """Called when a command is invoked"""
        self.commands_used += 1
        logger.info(f"Command '{ctx.command}' used by {ctx.author} in {ctx.guild}")

    async def on_command_error(self, ctx, error):
        """Enhanced error handling"""
        self.errors_count += 1
        
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏰ Command on cooldown. Try again in {error.retry_after:.1f}s")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ I don't have the required permissions to execute this command.")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ This command can't be used in private messages.")
        else:
            logger.error(f"Unhandled command error: {error}", exc_info=error)
            await ctx.send("❌ An unexpected error occurred. Please try again later.")

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle slash command errors"""
        self.errors_count += 1
        
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏰ Command on cooldown. Try again in {error.retry_after:.1f}s", 
                ephemeral=True
            )
        elif isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
        else:
            logger.error(f"Unhandled app command error: {error}", exc_info=error)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An unexpected error occurred. Please try again later.", 
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ An unexpected error occurred. Please try again later.", 
                        ephemeral=True
                    )
            except:
                pass

    async def load_all_cogs(self):
        """Load all cogs from the cogs directory"""
        startup_logger.info("📦 Starting cog loading process...")
        
        cogs_dir = "./cogs"
        if not os.path.exists(cogs_dir):
            startup_logger.error("❌ Cogs directory not found!")
            return

        for filename in os.listdir(cogs_dir):
            if filename.endswith(".py") and not filename.startswith("_"):
                cog_name = filename[:-3]
                try:
                    await self.load_cog(cog_name)
                except Exception as e:
                    startup_logger.critical(f"🔥 CRITICAL: Failed to load cog {cog_name}: {e}", exc_info=True)

        # Report loading results
        startup_logger.info(f"✅ Successfully loaded {len(self.loaded_cogs)} cogs")
        if self.failed_cogs:
            startup_logger.warning(f"❌ Failed to load {len(self.failed_cogs)} cogs: {list(self.failed_cogs.keys())}")
            for cog_name, error in self.failed_cogs.items():
                startup_logger.error(f"  - {cog_name}: {error}")

    async def load_cog(self, cog_name: str):
        """Load a single cog with enhanced error handling and logging"""
        startup_logger.info(f"🔄 Loading cog: {cog_name}")
        
        try:
            if cog_name not in self.loaded_cogs:
                # Load with timeout to prevent hanging
                await asyncio.wait_for(
                    self.load_extension(f"cogs.{cog_name}"),
                    timeout=10.0
                )
                self.loaded_cogs.add(cog_name)
                startup_logger.info(f"✅ Successfully loaded cog: {cog_name}")
            else:
                startup_logger.warning(f"⚠️ Cog {cog_name} already loaded")
                
        except asyncio.TimeoutError:
            error_msg = f"Timed out after 10 seconds"
            self.failed_cogs[cog_name] = error_msg
            startup_logger.error(f"❌ {cog_name}: {error_msg}")
            
        except commands.ExtensionAlreadyLoaded:
            startup_logger.warning(f"⚠️ Cog {cog_name} already loaded")
            self.loaded_cogs.add(cog_name)
            
        except commands.NoEntryPointError:
            error_msg = f"No setup function found"
            self.failed_cogs[cog_name] = error_msg
            startup_logger.error(f"❌ {cog_name}: {error_msg}")
            
        except commands.ExtensionFailed as e:
            error_msg = f"Setup function failed: {e.original}"
            self.failed_cogs[cog_name] = error_msg
            startup_logger.error(f"❌ {cog_name}: {error_msg}")
            
        except ImportError as e:
            error_msg = f"Import error: {e}"
            self.failed_cogs[cog_name] = error_msg
            startup_logger.error(f"❌ {cog_name}: {error_msg}")
            
        except Exception as e:
            self.failed_cogs[cog_name] = str(e)
            startup_logger.error(f"❌ {cog_name}: Unexpected error: {e}", exc_info=True)

    async def unload_cog(self, cog_name: str):
        """Unload a cog safely"""
        try:
            await self.unload_extension(f"cogs.{cog_name}")
            self.loaded_cogs.discard(cog_name)
            logger.info(f"🔄 Unloaded cog: {cog_name}")
        except Exception as e:
            logger.error(f"❌ Failed to unload cog {cog_name}: {e}")

    async def reload_cog(self, cog_name: str):
        """Reload a cog"""
        try:
            await self.reload_extension(f"cogs.{cog_name}")
            logger.info(f"🔄 Reloaded cog: {cog_name}")
        except Exception as e:
            logger.error(f"❌ Failed to reload cog {cog_name}: {e}")

    async def sync_commands(self):
        """Sync slash commands with timeout"""
        try:
            startup_logger.info("🔄 Syncing commands...")
            
            if GUILD_ID:
                guild = discord.Object(id=int(GUILD_ID))
                synced_guild = await asyncio.wait_for(
                    self.tree.sync(guild=guild), 
                    timeout=10.0
                )
                startup_logger.info(f"✅ Synced {len(synced_guild)} commands to guild {GUILD_ID}")
            
            synced_global = await asyncio.wait_for(
                self.tree.sync(), 
                timeout=10.0
            )
            startup_logger.info(f"✅ Synced {len(synced_global)} global commands")
            
        except asyncio.TimeoutError:
            startup_logger.error("❌ Command sync timed out after 10s")
        except Exception as e:
            startup_logger.error(f"❌ Command sync failed: {e}")

    async def change_status(self):
        """Change bot status"""
        try:
            status, activity = random.choice(self.status_options)
            await self.change_presence(status=status, activity=activity)
            logger.debug(f"🎭 Status changed to: {status.name} - {activity.name}")
        except Exception as e:
            logger.error(f"❌ Failed to change status: {e}")

    async def send_startup_notification(self):
        """Send startup notification via webhook"""
        if not PUBLIC_WEBHOOK:
            return
        
        try:
            import aiohttp
            
            embed_data = {
                "embeds": [{
                    "title": "🤖 BringusBot Started",
                    "description": f"Version {BOT_VERSION} is now online!",
                    "color": 0x00ff00,
                    "fields": [
                        {"name": "Guilds", "value": str(len(self.guilds)), "inline": True},
                        {"name": "Users", "value": str(len(set(self.get_all_members()))), "inline": True},
                        {"name": "Cogs", "value": str(len(self.loaded_cogs)), "inline": True}
                    ],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }]
            }
            
            async with aiohttp.ClientSession() as session:
                await asyncio.wait_for(
                    session.post(PUBLIC_WEBHOOK, json=embed_data),
                    timeout=5.0
                )
                
        except Exception as e:
            logger.error(f"❌ Failed to send startup notification: {e}")

    @tasks.loop(minutes=30)
    async def status_rotation(self):
        """Rotate bot status every 30 minutes"""
        await self.change_status()

    @status_rotation.before_loop
    async def before_status_rotation(self):
        """Wait for bot to be ready before starting status rotation"""
        await self.wait_until_ready()

    @tasks.loop(hours=1)
    async def periodic_tasks(self):
        """Run periodic maintenance tasks"""
        try:
            self.save_uptime_data()
            logger.info(f"📊 Stats - Commands: {self.commands_used}, Messages: {self.messages_seen}, Errors: {self.errors_count}")
            
            if hasattr(self, '_last_cleanup'):
                if time.time() - self._last_cleanup > 86400:  # 24 hours
                    await self.cleanup_old_data()
            else:
                self._last_cleanup = time.time()
                
        except Exception as e:
            logger.error(f"❌ Periodic task error: {e}")

    @periodic_tasks.before_loop
    async def before_periodic_tasks(self):
        """Wait for bot to be ready before starting periodic tasks"""
        await self.wait_until_ready()

    async def cleanup_old_data(self):
        """Clean up old database entries"""
        try:
            from utils.db import purge_old_data
            await asyncio.to_thread(purge_old_data)
            self._last_cleanup = time.time()
            logger.info("🧹 Old data cleanup completed")
        except Exception as e:
            logger.error(f"❌ Data cleanup failed: {e}")

    def get_uptime(self) -> str:
        """Get formatted uptime"""
        uptime_seconds = int(time.time() - self.start_time)
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m {seconds}s"
        return f"{hours}h {minutes}m {seconds}s"

# ─────────────────────────────────────────────────────────────────────────────
# Enhanced Status Control Cog
# ─────────────────────────────────────────────────────────────────────────────

class StatusControl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        startup_logger.info("✅ StatusControl cog initialized")

    def has_admin_permissions(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions"""
        if not interaction.guild:
            return False
        
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return False
            
        return member.guild_permissions.administrator

    @app_commands.command(name="setstatus", description="Change bot's status (Admin only)")
    @app_commands.describe(
        status="Bot status: online, idle, dnd, invisible",
        activity="Custom activity text",
        activity_type="Activity type: playing, watching, listening, streaming"
    )
    @app_commands.choices(status=[
        app_commands.Choice(name="Online", value="online"),
        app_commands.Choice(name="Idle", value="idle"),
        app_commands.Choice(name="Do Not Disturb", value="dnd"),
        app_commands.Choice(name="Invisible", value="invisible")
    ])
    @app_commands.choices(activity_type=[
        app_commands.Choice(name="Playing", value="playing"),
        app_commands.Choice(name="Watching", value="watching"),
        app_commands.Choice(name="Listening", value="listening"),
        app_commands.Choice(name="Streaming", value="streaming")
    ])
    async def setstatus(
        self,
        interaction: discord.Interaction,
        status: str,
        activity: str = "Being awesome!",
        activity_type: str = "playing"
    ):
        if not self.has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You need administrator permissions to use this command.", 
                ephemeral=True
            )
            return

        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible
        }

        activity_map = {
            "playing": lambda name: discord.Game(name),
            "watching": lambda name: discord.Activity(type=discord.ActivityType.watching, name=name),
            "listening": lambda name: discord.Activity(type=discord.ActivityType.listening, name=name),
            "streaming": lambda name: discord.Streaming(name=name, url="https://www.twitch.tv/morithegamer1")
        }

        try:
            bot_status = status_map.get(status.lower(), discord.Status.online)
            bot_activity = activity_map.get(activity_type.lower(), discord.Game)(activity)

            await self.bot.change_presence(status=bot_status, activity=bot_activity)
            
            embed = discord.Embed(
                title="✅ Status Updated",
                description=f"Status: **{status.title()}**\nActivity: **{activity_type.title()}** {activity}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
            
            logger.info(f"Status changed by {interaction.user}: {status} - {activity_type} {activity}")
            
        except Exception as e:
            logger.error(f"Status change failed: {e}")
            await interaction.response.send_message(
                "❌ Failed to change status. Please try again.", 
                ephemeral=True
            )

    @app_commands.command(name="botstats", description="View bot statistics")
    async def botstats(self, interaction: discord.Interaction):
        """Display comprehensive bot statistics"""
        embed = discord.Embed(
            title=f"📊 BringusBot Statistics",
            description=f"Version {BOT_VERSION}",
            color=discord.Color.blurple()
        )
        
        # Basic stats
        embed.add_field(
            name="🏠 Servers",
            value=f"{len(self.bot.guilds):,}",
            inline=True
        )
        embed.add_field(
            name="👥 Users",
            value=f"{len(set(self.bot.get_all_members())):,}",
            inline=True
        )
        embed.add_field(
            name="📝 Channels",
            value=f"{len(list(self.bot.get_all_channels())):,}",
            inline=True
        )
        
        # Performance stats
        embed.add_field(
            name="⏱️ Uptime",
            value=self.bot.get_uptime(),
            inline=True
        )
        embed.add_field(
            name="🎯 Commands Used",
            value=f"{self.bot.commands_used:,}",
            inline=True
        )
        embed.add_field(
            name="💬 Messages Seen",
            value=f"{self.bot.messages_seen:,}",
            inline=True
        )
        
        # Technical stats
        embed.add_field(
            name="🧩 Loaded Cogs",
            value=f"{len(self.bot.loaded_cogs)}",
            inline=True
        )
        embed.add_field(
            name="❌ Errors",
            value=f"{self.bot.errors_count:,}",
            inline=True
        )
        embed.add_field(
            name="🔄 Total Restarts",
            value=f"{self.bot.uptime_data.get('total_restarts', 0)}",
            inline=True
        )
        
        # Latency
        embed.add_field(
            name="🏓 Latency",
            value=f"{self.bot.latency*1000:.0f}ms",
            inline=True
        )
        
        embed.set_footer(text=f"Started: {datetime.fromtimestamp(self.bot.start_time).strftime('%Y-%m-%d %H:%M:%S')}")
        embed.timestamp = datetime.now(timezone.utc)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="reload", description="Reload a cog (Admin only)")
    @app_commands.describe(cog="Name of the cog to reload")
    async def reload_cog_command(self, interaction: discord.Interaction, cog: str):
        """Reload a specific cog"""
        if not self.has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ You need administrator permissions to use this command.", 
                ephemeral=True
            )
            return

        await interaction.response.defer()
        
        try:
            await self.bot.reload_cog(cog)
            embed = discord.Embed(
                title="✅ Cog Reloaded",
                description=f"Successfully reloaded `{cog}`",
                color=discord.Color.green()
            )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Reload Failed",
                description=f"Failed to reload `{cog}`: {str(e)}",
                color=discord.Color.red()
            )
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="cmds", description="Show all available commands")
    async def cmds(self, interaction: discord.Interaction):
        """Display all available bot commands"""
        embed = discord.Embed(
            title="🤖 BringusBot Commands",
            description=f"All available commands for {BOT_VERSION}",
            color=discord.Color.blue()
        )
        
        # Main bot commands
        main_commands = [
            "`/botstats` - View bot statistics",
            "`/setstatus` - Change bot status (Admin)",
            "`/reload` - Reload a cog (Admin)",
            "`/cmds` - Show this help menu"
        ]
        embed.add_field(name="🔧 Main Commands", value="\n".join(main_commands), inline=False)
        
        # Get commands from loaded cogs
        cog_commands = {}
        for cog_name in self.bot.cogs:
            cog = self.bot.get_cog(cog_name)
            if cog and hasattr(cog, '__cog_app_commands__'):
                commands_list = []
                for cmd in cog.__cog_app_commands__:
                    if hasattr(cmd, 'name') and hasattr(cmd, 'description'):
                        commands_list.append(f"`/{cmd.name}` - {cmd.description}")
                
                if commands_list and cog_name != "StatusControl":
                    cog_commands[cog_name] = commands_list
        
        # Add cog commands to embed
        for cog_name, commands in cog_commands.items():
            if commands:
                command_text = "\n".join(commands[:10])
                if len(commands) > 10:
                    command_text += f"\n... and {len(commands) - 10} more"
                
                embed.add_field(
                    name=f"📂 {cog_name}",
                    value=command_text,
                    inline=False
                )
        
        # Add footer with additional info
        total_commands = len(main_commands) + sum(len(cmds) for cmds in cog_commands.values())
        embed.set_footer(
            text=f"Total Commands: {total_commands} | Loaded Cogs: {len(self.bot.loaded_cogs)}"
        )
        embed.timestamp = datetime.now(timezone.utc)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ─────────────────────────────────────────────────────────────────────────────
# Signal Handling & Graceful Shutdown
# ─────────────────────────────────────────────────────────────────────────────

def setup_signal_handlers(bot):
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        asyncio.create_task(shutdown_bot(bot))
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def shutdown_bot(bot):
    """Gracefully shutdown the bot"""
    try:
        logger.info("🛑 Shutting down BringusBot...")
        
        # Cancel all tasks
        for task in asyncio.all_tasks():
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
        
        # Save uptime data
        bot.save_uptime_data()
        
        # Close bot connection
        if not bot.is_closed():
            await bot.close()
        
        # Give time for cleanup
        await asyncio.sleep(1)
        
        logger.info("✅ BringusBot shutdown complete")
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Main Function
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    """Main bot startup function with enhanced error handling"""
    startup_logger.info("🚀 Starting BringusBot main function...")
    
    # Create bot instance
    bot = BringusBot()
    
    # Setup signal handlers
    setup_signal_handlers(bot)
    
    # Add status control cog
    startup_logger.info("🔧 Adding StatusControl cog...")
    await bot.add_cog(StatusControl(bot))
    
    # Check Discord connectivity
    connectivity_ok = await check_discord_connectivity()
    if not connectivity_ok:
        startup_logger.warning("⚠️ Discord connectivity test failed, but continuing anyway...")
    
    try:
        # Start the bot with retry logic
        startup_logger.info("🚀 Starting Discord bot connection...")
        if DISCORD_TOKEN is None:
            startup_logger.critical("❌ DISCORD_TOKEN is None - cannot start bot!")
            sys.exit(1)
            
        # Validate token format
        if not DISCORD_TOKEN.startswith(('Bot ', 'Bearer ')):
            # Assume it's a bot token and needs the Bot prefix
            token_to_use = DISCORD_TOKEN
        else:
            token_to_use = DISCORD_TOKEN
            
        # Try connection with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                startup_logger.info(f"🔌 Connection attempt {attempt + 1}/{max_retries}")
                await bot.start(token_to_use)
                break  # If we get here, connection succeeded
                
            except asyncio.TimeoutError:
                startup_logger.error(f"❌ Connection attempt {attempt + 1} timed out after 120s")
                if attempt < max_retries - 1:
                    startup_logger.info(f"⏳ Retrying in 10 seconds...")
                    await asyncio.sleep(10)
                    continue
                else:
                    startup_logger.critical("❌ All connection attempts failed!")
                    raise
                    
            except discord.LoginFailure as e:
                startup_logger.critical(f"❌ Discord login failed - check your bot token: {e}")
                sys.exit(1)
                
            except discord.HTTPException as e:
                startup_logger.error(f"❌ Discord HTTP error: {e}")
                if attempt < max_retries - 1:
                    startup_logger.info(f"⏳ Retrying in 15 seconds...")
                    await asyncio.sleep(15)
                    continue
                else:
                    raise
                    
            except Exception as e:
                startup_logger.error(f"❌ Unexpected connection error: {e}")
                if attempt < max_retries - 1:
                    startup_logger.info(f"⏳ Retrying in 20 seconds...")
                    await asyncio.sleep(20)
                    continue
                else:
                    raise
            

    except KeyboardInterrupt:
        startup_logger.info("👋 Bot stopped by user")
    except Exception as e:
        startup_logger.critical(f"💥 Critical startup error: {e}", exc_info=True)
        
        # Log crash for debugging
        crash_info = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
            "type": type(e).__name__
        }
        bot.uptime_data["crash_log"].append(crash_info)
        bot.save_uptime_data()
        
        raise
    finally:
        await shutdown_bot(bot)

async def check_discord_connectivity():
    """Check if we can reach Discord's API"""
    try:
        import aiohttp
        startup_logger.info("🌐 Testing Discord API connectivity...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://discord.com/api/v10/gateway", 
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    startup_logger.info(f"✅ Discord API reachable: {data.get('url', 'Unknown gateway')}")
                    return True
                else:
                    startup_logger.error(f"❌ Discord API returned status {resp.status}")
                    return False
    except Exception as e:
        startup_logger.error(f"❌ Cannot reach Discord API: {e}")
        return False

# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        startup_logger.info("🎬 BringusBot starting...")
        asyncio.run(main())
    except KeyboardInterrupt:
        startup_logger.info("👋 Goodbye!")
    except Exception as e:
        startup_logger.critical(f"💥 Fatal startup error: {e}", exc_info=True)
        sys.exit(1)
