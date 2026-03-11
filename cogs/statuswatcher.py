import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
from typing import Optional
from utils.db import init_db, purge_old_data
from utils.fluxymode import is_fluxy_mode_enabled
from utils.theming import themed_embed

class PresenceWatcher(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.admin_ids = [bot.owner_id or 785194743293673493]  # Default to bot owner ID
        self.last_seen = None
        self.status_log_channel_id = None

    @app_commands.command(name="ownerstatus", description="See what the bot owner is currently doing!")
    async def ownerstatus(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = RefreshPresenceView(self, interaction.user)
        try:
            embed = await self.build_status_embed(interaction.guild)
            print(f"Embed ready for: {interaction.user.name}")
            await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            print(f"❗ Error in /ownerstatus: {e}")
            await interaction.followup.send(content="An error occurred while building the status embed.", ephemeral=True)

    async def build_status_embed(self, guild: Optional[discord.Guild]) -> discord.Embed:
        if not guild:
            return discord.Embed(description="❌ This command only works in servers.")

        owner = None
        for admin_id in self.admin_ids:
            try:
                owner = guild.get_member(admin_id) or await guild.fetch_member(admin_id)
            except Exception:
                owner = None
            if owner:
                break

        if not owner:
            return discord.Embed(description="❌ Owner/admin not found in this server.")

        embed = themed_embed(title="🦊 WebFlux Labs • Owner Status")
        embed.set_author(name=owner.display_name, icon_url=owner.display_avatar.url)
        embed.set_thumbnail(url=owner.display_avatar.url)

        embed.add_field(name="Presence", value=str(owner.status).title(), inline=True)
        embed.add_field(name="Mobile", value="📱 Yes" if owner.is_on_mobile() else "💻 No", inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)

        activity_info = ""
        has_activity = False

        for activity in owner.activities:
            has_activity = True
            if isinstance(activity, discord.Game):
                emoji = self.get_app_emoji(activity.name)
                activity_info += f"{emoji} Playing **{activity.name}**\n"

            elif isinstance(activity, discord.Streaming):
                activity_info += f"📺 Streaming **{activity.name}** on `{activity.platform}`\n"

            elif isinstance(activity, discord.Spotify):
                try:
                    progress = (datetime.now(timezone.utc) - activity.start).total_seconds()
                    total = activity.duration.total_seconds()
                    percent = min(progress / total, 1.0)
                    bars = int(percent * 10)
                    bar = f"{'▰'*bars}{'▱'*(10-bars)}"

                    current_time = f"{int(progress//60)}:{int(progress%60):02}"
                    total_time = f"{int(total//60)}:{int(total%60):02}"

                    activity_info += (
                        f"🎵 Listening to: **{activity.title}**\n"
                        f"By: `{activity.artist}`\n"
                        f"{bar} `{current_time} / {total_time}`\n"
                        f"[Open in Spotify]({activity.track_url})"
                    )
                    embed.set_thumbnail(url=activity.album_cover_url)
                except Exception as e:
                    activity_info += f"🎵 Listening to: **{activity.title}** (⚠️ Error calculating progress)\n"

            elif hasattr(discord, "CustomActivity") and isinstance(activity, discord.CustomActivity):
                activity_info += f"💬 Custom Status: {activity.name or activity.emoji}\n"

            elif isinstance(activity, discord.Activity):
                name = activity.name or "Unknown App"
                details = f" — {activity.details}" if getattr(activity, "details", None) else ""
                if "code" in name.lower():
                    activity_info += f"🧠 Coding in: **{name}**{details}\n"
                elif "vrchat" in name.lower():
                    activity_info += f"🦾 Exploring in: **{name}**{details}\n"
                elif "unity" in name.lower():
                    activity_info += f"🎮 Developing in: **{name}**{details}\n"
                elif "steam" in name.lower():
                    activity_info += f"🔥 Gaming via: **{name}**{details}\n"
                else:
                    activity_info += f"💻 Using: **{name}**{details}\n"

        if has_activity:
            embed.add_field(name="Current Activity", value=activity_info, inline=False)
        else:
            embed.add_field(name="Current Activity", value="Nothing right now!", inline=False)

        if owner.status == discord.Status.offline:
            if not self.last_seen:
                self.last_seen = datetime.utcnow()
            embed.add_field(
                name="⏳ Last Seen",
                value=f"<t:{int(self.last_seen.timestamp())}:R>",
                inline=False
            )

        # Optional debug info footer
        embed.set_footer(text=f"Debug ID: {owner.id} • Join Date: {owner.joined_at.strftime('%Y-%m-%d') if owner.joined_at else 'N/A'}")

        return embed

    def get_app_emoji(self, name: str) -> str:
        key = name.lower()
        if "minecraft" in key:
            return "⛏️"
        if "vscode" in key or "visual studio" in key:
            return "🧠"
        if "unity" in key:
            return "🕹️"
        if "roblox" in key:
            return "🧱"
        if "league" in key:
            return "⚔️"
        if "chrome" in key:
            return "🌐"
        if "discord" in key:
            return "💬"
        if "spotify" in key:
            return "🎵"
        return "🎮"

    @tasks.loop(seconds=60)
    async def sync_owner_status(self):
        for guild in self.bot.guilds:
            for admin_id in self.admin_ids:
                owner = guild.get_member(admin_id) or await guild.fetch_member(admin_id)
                if not owner:
                    continue
                for activity in owner.activities:
                    if isinstance(activity, discord.Game):
                        await self.bot.change_presence(activity=discord.Game(name=activity.name))
                        return
                    elif isinstance(activity, discord.CustomActivity) and activity.name:
                        await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.custom, name=activity.name))
                        return
                    elif isinstance(activity, discord.Spotify):
                        await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=activity.title))
                        return

class RefreshPresenceView(discord.ui.View):
    def __init__(self, cog: PresenceWatcher, requester: discord.abc.User, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.requester = requester

    @discord.ui.button(label="🔁", style=discord.ButtonStyle.blurple)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.label = "🔁 Fluxy Refresh" if is_fluxy_mode_enabled() else "🔁 Refresh"
        if interaction.user.id != self.requester.id:
            await interaction.response.send_message("Only the original requester can refresh this.", ephemeral=True)
            return
        embed = await self.cog.build_status_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

async def setup(bot):
    await bot.add_cog(PresenceWatcher(bot))


# This cog allows users to check the status of the bot owner, including their current activities.
# It uses the `owner_id` to fetch the owner's presence and activities, displaying them in an embed.
# Make sure to replace `owner_id` with your actual Discord user ID to make it functional.
# The command can be invoked with `/ownerstatus` in any server where the bot is present.
# The embed will show the owner's status and any ongoing activities like playing games, streaming, or listening to music.
# If the owner is not found in the server, it will notify the user accordingly.