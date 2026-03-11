import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncpraw
import random
import os
import typing
import asyncio
import json
import aiohttp
from datetime import datetime, timedelta
from openai import OpenAI
import re
import logging

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET = os.getenv("REDDIT_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

reddit = asyncpraw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_SECRET,
    user_agent="BringusBot:v3.0 (by u/Impossible-Ad7445)"
)

try:
    client = OpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    print(f"OpenAI init failed: {e}")
    client = None

SFW_SUBREDDITS = [
    "memes", "dankmemes", "wholesomememes", "funny", "meirl", "me_irl",
    "ProgrammerHumor", "gaming", "PrequelMemes", "animemes", "dogelore",
    "okbuddyretard", "surrealmemes", "deepfriedmemes", "antimeme"
]

NSFW_SUBREDDITS = [
    "NSFWmemes", "darkmemes", "hentai_memes", "rule34", "NSFW_GIF",
    "nsfwfunny", "AdultHumor", "NSFWFunny"
]

MEME_CATEGORIES = {
    "programming": ["ProgrammerHumor", "softwaregore", "programmingmemes"],
    "gaming": ["gaming", "gamingmemes", "MinecraftMemes", "tf2"],
    "anime": ["animemes", "anime_irl", "Animemes"],
    "dank": ["dankmemes", "deepfriedmemes", "nukedmemes"],
    "wholesome": ["wholesomememes", "MadeMeSmile", "aww"],
    "cursed": ["cursedimages", "cursedcomments", "blursedimages"]
}

class MemeStats:
    def __init__(self):
        self.user_stats = {}
        self.subreddit_stats = {}
        self.daily_memes = 0
        self.last_reset = datetime.now().date()
    
    def add_meme_request(self, user_id: int, subreddit: str):
        # Reset daily counter if new day
        if datetime.now().date() > self.last_reset:
            self.daily_memes = 0
            self.last_reset = datetime.now().date()
        
        self.daily_memes += 1
        
        # User stats
        if user_id not in self.user_stats:
            self.user_stats[user_id] = {"total": 0, "last_request": None}
        self.user_stats[user_id]["total"] += 1
        self.user_stats[user_id]["last_request"] = datetime.now()
        
        # Subreddit stats
        if subreddit not in self.subreddit_stats:
            self.subreddit_stats[subreddit] = 0
        self.subreddit_stats[subreddit] += 1

class MemeView(discord.ui.View):
    def __init__(self, cog, subreddit: str, nsfw_allowed: bool):
        super().__init__(timeout=300)
        self.cog = cog
        self.subreddit = subreddit
        self.nsfw_allowed = nsfw_allowed

    @discord.ui.button(label="🔄 New Meme", style=discord.ButtonStyle.primary)
    async def new_meme(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        title, url, permalink, blocked = await self.cog.fetch_meme(self.subreddit, self.nsfw_allowed)
        
        if blocked or not url:
            await interaction.followup.send("❌ Failed to fetch new meme.", ephemeral=True)
            return
        
        rating = await self.cog.rate_title_with_ai(title) if title else "No title available."
        embed = discord.Embed(
            title=title or "No Title",
            description=f"🌐 [Source]({permalink})\n🧠 {rating}",
            color=discord.Color.red() if self.nsfw_allowed else discord.Color.blurple()
        )
        embed.set_image(url=url)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="⭐ Rate", style=discord.ButtonStyle.secondary)
    async def rate_meme(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = MemeRatingModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📊 Stats", style=discord.ButtonStyle.secondary)
    async def show_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        stats_embed = self.cog.create_stats_embed(interaction.user.id)
        await interaction.response.send_message(embed=stats_embed, ephemeral=True)

class MemeRatingModal(discord.ui.Modal, title="Rate this meme!"):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    rating = discord.ui.TextInput(
        label="Rating (1-10)",
        placeholder="Enter a number from 1 to 10...",
        max_length=2,
        required=True
    )

    comment = discord.ui.TextInput(
        label="Comment (Optional)",
        placeholder="What did you think about this meme?",
        max_length=200,
        required=False,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating_num = int(self.rating.value)
            if not 1 <= rating_num <= 10:
                await interaction.response.send_message("❌ Rating must be between 1 and 10!", ephemeral=True)
                return
            
            response = f"⭐ You rated this meme: **{rating_num}/10**"
            if self.comment.value:
                response += f"\n💬 Comment: *{self.comment.value}*"
            
            await interaction.response.send_message(response, ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number!", ephemeral=True)

class MemeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stats = MemeStats()
        self.meme_cache = {}
        self.last_cache_clear = datetime.now()
        self.user_cooldowns = {}

    async def cog_load(self):
        """Start background tasks when cog loads - AFTER bot ready"""
        # Don't start tasks immediately - wait for bot to be fully ready
        pass

    async def start_background_tasks(self):
        """Start background tasks after bot is ready"""
        try:
            if not hasattr(self, 'clear_cache') or not self.clear_cache.is_running():
                self.clear_cache.start()
            if not hasattr(self, 'update_subreddit_list') or not self.update_subreddit_list.is_running():
                self.update_subreddit_list.start()
            print("✅ Meme cog background tasks started")
        except Exception as e:
            logging.error(f"Failed to start meme cog tasks: {e}")

    async def cog_unload(self):
        """Clean shutdown of background tasks"""
        try:
            if hasattr(self, 'clear_cache') and self.clear_cache.is_running():
                self.clear_cache.cancel()
            if hasattr(self, 'update_subreddit_list') and self.update_subreddit_list.is_running():
                self.update_subreddit_list.cancel()
            print("🛑 Meme cog background tasks stopped")
        except Exception as e:
            logging.error(f"Error stopping meme cog tasks: {e}")

    @tasks.loop(hours=1)
    async def clear_cache(self):
        """Clear meme cache every hour - non-blocking version"""
        try:
            cache_size = sum(len(memes) for memes in self.meme_cache.values())
            self.meme_cache.clear()
            self.last_cache_clear = datetime.now()
            print(f"🧹 Meme cache cleared (was {cache_size} items)")
            
            # Force garbage collection in Docker environments
            import gc
            gc.collect()
            
        except Exception as e:
            logging.error(f"Cache clear error: {e}")

    @clear_cache.before_loop
    async def before_clear_cache(self):
        """Wait for bot to be ready before starting cache clear loop"""
        await self.bot.wait_until_ready()
        print("🔄 Cache clear task ready")

    @tasks.loop(hours=6)
    async def update_subreddit_list(self):
        """Update popular subreddit lists - with timeout and error handling"""
        try:
            print("📈 Starting subreddit list update...")
            
            # Use asyncio.wait_for to prevent hanging
            popular_subs = await asyncio.wait_for(
                self.get_trending_subreddits(), 
                timeout=30.0  # 30 second timeout
            )
            
            if popular_subs:
                # Only add new subreddits, don't duplicate
                new_subs = [sub for sub in popular_subs[:5] if sub not in SFW_SUBREDDITS]
                SFW_SUBREDDITS.extend(new_subs)
                print(f"📈 Updated subreddit list with {len(new_subs)} new trending subs: {new_subs}")
            else:
                print("📈 No new trending subreddits found")
                
        except asyncio.TimeoutError:
            print("⏰ Subreddit update timed out after 30 seconds")
        except Exception as e:
            logging.error(f"Failed to update subreddit list: {e}")

    @update_subreddit_list.before_loop
    async def before_update_subreddit_list(self):
        """Wait for bot to be ready before starting subreddit update loop"""
        await self.bot.wait_until_ready()
        # Add initial delay to prevent startup conflicts
        await asyncio.sleep(60)  # Wait 1 minute after bot ready
        print("🔄 Subreddit update task ready")

    async def get_trending_subreddits(self):
        """Fetch trending subreddits with proper error handling and timeout"""
        try:
            print("🔍 Fetching trending subreddits...")
            
            # Create a fresh Reddit instance with timeout
            temp_reddit = asyncpraw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_SECRET,
                user_agent="BringusBot:v3.0 (by u/Impossible-Ad7445)",
                timeout=15  # 15 second timeout for requests
            )
            
            subreddit = await temp_reddit.subreddit("popular")
            trending = []
            count = 0
            
            async for post in subreddit.hot(limit=25):  # Increased limit for better variety
                if count >= 10:  # Safety limit
                    break
                    
                sub_name = post.subreddit.display_name
                if (sub_name not in trending and 
                    sub_name not in SFW_SUBREDDITS and 
                    len(sub_name) < 30 and  # Avoid overly long names
                    not post.over_18):  # Only SFW subreddits
                    trending.append(sub_name)
                    
                count += 1
                
                # Yield control periodically
                if count % 5 == 0:
                    await asyncio.sleep(0.1)
            
            await temp_reddit.close()  # Clean up connection
            print(f"🔍 Found {len(trending)} trending subreddits")
            return trending[:5]
            
        except Exception as e:
            logging.error(f"Error fetching trending subreddits: {e}")
            return []

    def is_user_on_cooldown(self, user_id: int) -> bool:
        """Check if user is on cooldown"""
        if user_id not in self.user_cooldowns:
            return False
        
        cooldown_time = self.user_cooldowns[user_id]
        return datetime.now() < cooldown_time

    def set_user_cooldown(self, user_id: int, seconds: int = 5):
        """Set cooldown for user"""
        self.user_cooldowns[user_id] = datetime.now() + timedelta(seconds=seconds)

    async def fetch_meme(self, subreddit_name: str, nsfw_allowed: bool):
        """Enhanced meme fetching with caching and better filtering"""
        cache_key = f"{subreddit_name}_{nsfw_allowed}"
        
        # Check cache first
        if cache_key in self.meme_cache:
            cached_memes = self.meme_cache[cache_key]
            if cached_memes:
                return cached_memes.pop()
        
        try:
            # Use timeout for Reddit requests
            subreddit = await asyncio.wait_for(
                reddit.subreddit(subreddit_name, fetch=True),
                timeout=10.0
            )
            
            if subreddit.over18 and not nsfw_allowed:
                return None, None, None, True

            valid_memes = []
            count = 0
            
            async for post in subreddit.hot(limit=50):
                if count >= 20:  # Safety limit
                    break
                    
                if post.stickied or post.is_self:
                    continue
                
                # Filter for image posts
                if self.is_valid_image_post(post):
                    meme_data = (
                        post.title,
                        post.url,
                        f"https://reddit.com{post.permalink}",
                        False
                    )
                    valid_memes.append(meme_data)
                
                count += 1
                
                # Yield control periodically
                if count % 10 == 0:
                    await asyncio.sleep(0.1)
                
                if len(valid_memes) >= 10:  # Cache up to 10 memes
                    break
            
            if valid_memes:
                # Cache remaining memes
                self.meme_cache[cache_key] = valid_memes[1:]
                return valid_memes[0]
            
            return None, None, None, False
            
        except asyncio.TimeoutError:
            logging.warning(f"Timeout fetching from {subreddit_name}")
            return None, None, None, False
        except Exception as e:
            logging.error(f"Error fetching from {subreddit_name}: {e}")
            return None, None, None, False

    def is_valid_image_post(self, post) -> bool:
        """Check if post contains a valid image"""
        try:
            url = post.url.lower()
            image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
            
            # Direct image links
            if any(url.endswith(ext) for ext in image_extensions):
                return True
            
            # Common image hosts
            image_hosts = ['i.redd.it', 'i.imgur.com', 'imgur.com']
            if any(host in url for host in image_hosts):
                return True
            
            return False
        except Exception:
            return False

    async def rate_title_with_ai(self, title: str) -> str:
        """Enhanced AI rating with different personalities and timeout"""
        if client is None:
            return "🤖 (OpenAI not available)"
        
        try:
            personalities = [
                "You are a sarcastic meme critic who gives brutal but funny ratings.",
                "You are an enthusiastic Gen Z meme reviewer who uses lots of slang.",
                "You are a sophisticated meme connoisseur who analyzes humor academically.",
                "You are a chaotic meme goblin who rates everything with pure energy."
            ]
            
            personality = random.choice(personalities)
            
            # Use asyncio timeout for OpenAI calls
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.chat.completions.create,
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": personality},
                        {"role": "user", "content": f"Rate this meme title in one sentence: '{title}'"}
                    ],
                    max_tokens=50,
                    timeout=10
                ),
                timeout=15.0
            )
            
            content = response.choices[0].message.content
            return content.strip() if content is not None else "🤖 (No rating returned)"
            
        except asyncio.TimeoutError:
            return "🤖 (Rating timed out)"
        except Exception as e:
            return f"🤖 (Rating failed)"

    def create_stats_embed(self, user_id: typing.Optional[int] = None) -> discord.Embed:
        """Create statistics embed"""
        embed = discord.Embed(title="📊 Meme Bot Statistics", color=discord.Color.gold())
        
        # Global stats
        embed.add_field(
            name="🌍 Global Stats",
            value=f"Daily memes: {self.stats.daily_memes}\nTotal users: {len(self.stats.user_stats)}",
            inline=True
        )
        
        # Top subreddits
        if self.stats.subreddit_stats:
            top_subs = sorted(self.stats.subreddit_stats.items(), key=lambda x: x[1], reverse=True)[:5]
            sub_text = "\n".join([f"{sub}: {count}" for sub, count in top_subs])
            embed.add_field(name="🔥 Popular Subreddits", value=sub_text, inline=True)
        
        # User personal stats
        if user_id and user_id in self.stats.user_stats:
            user_data = self.stats.user_stats[user_id]
            last_request = user_data['last_request']
            last_time = last_request.strftime('%H:%M') if last_request else "Never"
            embed.add_field(
                name="👤 Your Stats",
                value=f"Total memes: {user_data['total']}\nLast request: {last_time}",
                inline=True
            )
        
        cache_size = sum(len(memes) for memes in self.meme_cache.values())
        embed.set_footer(text=f"Cache size: {cache_size} | Last cleared: {self.last_cache_clear.strftime('%H:%M')}")
        return embed

    @app_commands.command(name="meme", description="Fetch a random meme from Reddit")
    @app_commands.describe(
        subreddit="Specific subreddit to fetch from",
        category="Meme category (programming, gaming, anime, etc.)"
    )
    async def meme(
        self,
        interaction: discord.Interaction,
        subreddit: typing.Optional[str] = None,
        category: typing.Optional[str] = None
    ):
        # Cooldown check
        if self.is_user_on_cooldown(interaction.user.id):
            await interaction.response.send_message("⏰ Please wait a moment before requesting another meme!", ephemeral=True)
            return

        nsfw = getattr(interaction.channel, "is_nsfw", lambda: False)()
        
        # Determine subreddit
        if subreddit:
            chosen_sub = subreddit
        elif category and category.lower() in MEME_CATEGORIES:
            chosen_sub = random.choice(MEME_CATEGORIES[category.lower()])
        else:
            chosen_sub = random.choice(SFW_SUBREDDITS if not nsfw else SFW_SUBREDDITS + NSFW_SUBREDDITS)

        await interaction.response.defer()
        
        title, url, permalink, blocked = await self.fetch_meme(chosen_sub, nsfw)
        
        if blocked:
            await interaction.followup.send(f"❌ The subreddit `{chosen_sub}` is NSFW. Use this command in an NSFW channel.", ephemeral=True)
            return
        if not url:
            await interaction.followup.send(f"⚠️ Couldn't fetch meme from `{chosen_sub}`.", ephemeral=True)
            return

        # Update stats
        self.stats.add_meme_request(interaction.user.id, chosen_sub)
        self.set_user_cooldown(interaction.user.id)

        # Generate AI rating
        rating = await self.rate_title_with_ai(title) if title else "No title available."
        
        embed = discord.Embed(
            title=title or "No Title",
            description=f"🌐 [Source]({permalink})\n🧠 {rating}",
            color=discord.Color.blurple()
        )
        embed.set_image(url=url)
        embed.set_footer(text=f"From r/{chosen_sub} • Requested by {interaction.user.display_name}")

        view = MemeView(self, chosen_sub, nsfw)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="nsfwmeme", description="Get a spicy meme from a NSFW subreddit!")
    @app_commands.describe(subreddit="Optional NSFW subreddit name")
    async def nsfwmeme(self, interaction: discord.Interaction, subreddit: typing.Optional[str] = None):
        nsfw = getattr(interaction.channel, "is_nsfw", None)
        is_nsfw = nsfw() if callable(nsfw) else False
        
        if not is_nsfw:
            await interaction.response.send_message("❌ NSFW memes only allowed in NSFW channels!", ephemeral=True)
            return

        if self.is_user_on_cooldown(interaction.user.id):
            await interaction.response.send_message("⏰ Please wait a moment before requesting another meme!", ephemeral=True)
            return

        chosen_sub = subreddit or random.choice(NSFW_SUBREDDITS)
        await interaction.response.defer()
        
        title, url, permalink, blocked = await self.fetch_meme(chosen_sub, True)
        
        if not url:
            await interaction.followup.send(f"⚠️ Couldn't fetch meme from `{chosen_sub}`.", ephemeral=True)
            return

        # Update stats
        self.stats.add_meme_request(interaction.user.id, chosen_sub)
        self.set_user_cooldown(interaction.user.id)

        rating = await self.rate_title_with_ai(title) if title else "No title available."
        
        embed = discord.Embed(
            title=title or "No Title",
            description=f"🔞 [Source]({permalink})\n🧠 {rating}",
            color=discord.Color.red()
        )
        embed.set_image(url=url)
        embed.set_footer(text=f"From r/{chosen_sub} • Requested by {interaction.user.display_name}")

        view = MemeView(self, chosen_sub, True)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="memestats", description="View meme bot statistics")
    async def memestats(self, interaction: discord.Interaction):
        stats_embed = self.create_stats_embed(interaction.user.id)
        await interaction.response.send_message(embed=stats_embed)

    @app_commands.command(name="memehelp", description="Show available meme categories and commands")
    async def memehelp(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🎭 Meme Bot Help", color=discord.Color.blue())
        
        # Categories
        categories_text = "\n".join([f"**{cat}**: {', '.join(subs[:3])}" for cat, subs in MEME_CATEGORIES.items()])
        embed.add_field(name="📂 Categories", value=categories_text, inline=False)
        
        # Commands
        commands_text = """
        `/meme` - Get a random meme
        `/meme subreddit:funny` - Get meme from specific subreddit
        `/meme category:gaming` - Get meme from category
        `/nsfwmeme` - Get NSFW meme (NSFW channels only)
        `/memestats` - View statistics
        `/memehelp` - Show this help
        """
        embed.add_field(name="🤖 Commands", value=commands_text, inline=False)
        
        embed.set_footer(text="Use the buttons on meme posts for more interactions!")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(MemeCog(bot))