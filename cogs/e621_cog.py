import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import base64
import os
import random
import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from collections import defaultdict
import re
import logging
from urllib.parse import quote_plus  # Added for safe query encoding

# Load environment variables
load_dotenv()

E621_USERNAME = os.getenv("E621_USERNAME")
E621_API_KEY = os.getenv("E621_API_KEY")
MODLOG_CHANNEL_ID = int(os.getenv("MODLOG_CHANNEL_ID", 0)) if os.getenv("MODLOG_CHANNEL_ID") else None
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class E621Cache:
    """Caching system for e621 posts to reduce API calls"""
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        self.cache = {}
        self.timestamps = {}
        self.max_size = max_size
        self.ttl = ttl  # Time to live in seconds
    
    def get(self, key: str) -> Optional[List[Dict]]:
        if key in self.cache:
            if time.time() - self.timestamps[key] < self.ttl:
                return self.cache[key]
            else:
                del self.cache[key]
                del self.timestamps[key]
        return None
    
    def set(self, key: str, value: List[Dict]):
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
            if self.timestamps:  # Check if timestamps exist
                oldest_key = min(self.timestamps.keys(), key=lambda k: self.timestamps[k])
                if oldest_key in self.cache:
                    del self.cache[oldest_key]
                if oldest_key in self.timestamps:
                    del self.timestamps[oldest_key]
        
        self.cache[key] = value
        self.timestamps[key] = time.time()

class UserStats:
    """Track user statistics and preferences"""
    def __init__(self):
        self.user_data: Dict[int, Dict[str, Any]] = defaultdict(lambda: {
            "searches": 0,
            "favorite_tags": defaultdict(int),
            "last_search": None,
            "blocked_tags": set(),
            "search_history": [],
            "daily_searches": 0,
            "last_daily_reset": datetime.utcnow().date()
        })
    
    def add_search(self, user_id: int, query: str, tags: List[str]):
        user = self.user_data[user_id]
        
        # Reset daily counter if new day
        current_date = datetime.utcnow().date()
        last_reset = user["last_daily_reset"]
        if not isinstance(last_reset, type(current_date)) or last_reset < current_date:
            user["daily_searches"] = 0
            user["last_daily_reset"] = current_date
        
        # Ensure searches is an integer before incrementing
        if not isinstance(user["searches"], int):
            user["searches"] = 0
        if not isinstance(user["daily_searches"], int):
            user["daily_searches"] = 0
            
        user["searches"] += 1
        user["daily_searches"] += 1
        user["last_search"] = datetime.utcnow()
        
        # Track favorite tags
        for tag in tags[:10]:  # Limit to first 10 tags
            if tag:  # Ensure tag is not empty
                user["favorite_tags"][tag] += 1
        
        # Add to search history (keep last 20)
        user["search_history"].append({
            "query": query,
            "timestamp": datetime.utcnow().isoformat(),
            "tags": tags[:5]
        })
        if len(user["search_history"]) > 20:
            user["search_history"].pop(0)
    
    def get_top_tags(self, user_id: int, limit: int = 5) -> List[tuple]:
        user = self.user_data[user_id]
        return sorted(user["favorite_tags"].items(), key=lambda x: x[1], reverse=True)[:limit]
    
    def is_rate_limited(self, user_id: int, max_daily: int = 50) -> bool:
        user = self.user_data[user_id]
        return user["daily_searches"] >= max_daily

class NSFWConfirmView(discord.ui.View):
    def __init__(self, cog, query: str, *, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.query = query

    @discord.ui.button(label="✅ View", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.edit_message(content="🔞 Loading NSFW content...", view=None)
            await self.cog.send_results(interaction, self.query)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.edit_message(content="❌ Cancelled.", view=None)
        except Exception:
            pass

class E621PostView(discord.ui.View):
    """Interactive view for e621 posts with navigation and actions"""
    def __init__(self, cog, posts: List[Dict], current_index: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.posts = posts
        self.current_index = current_index
        self.update_buttons()
    
    def update_buttons(self):
        # Iterate over children to set disabled states (avoids static type errors)
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label and 'Previous' in child.label:
                    child.disabled = self.current_index <= 0
                elif child.label and 'Next' in child.label:
                    child.disabled = self.current_index >= len(self.posts) - 1
    
    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_index > 0:
            self.current_index -= 1
            self.update_buttons()
            try:
                embed = self.cog.create_post_embed(self.posts[self.current_index], self.current_index + 1, len(self.posts))
                await interaction.response.edit_message(embed=embed, view=self)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_index < len(self.posts) - 1:
            self.current_index += 1
            self.update_buttons()
            try:
                embed = self.cog.create_post_embed(self.posts[self.current_index], self.current_index + 1, len(self.posts))
                await interaction.response.edit_message(embed=embed, view=self)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="🎲 Random", style=discord.ButtonStyle.primary)
    async def random_post(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.posts:
            self.current_index = random.randint(0, len(self.posts) - 1)
            self.update_buttons()
            try:
                embed = self.cog.create_post_embed(self.posts[self.current_index], self.current_index + 1, len(self.posts))
                await interaction.response.edit_message(embed=embed, view=self)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="ℹ️ Info", style=discord.ButtonStyle.success)
    async def post_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            post = self.posts[self.current_index]
            info_embed = self.cog.create_detailed_info_embed(post)
            await interaction.response.send_message(embed=info_embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

class E621(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cache = E621Cache()
        self.user_stats = UserStats()
        self.rate_limits = defaultdict(lambda: {"count": 0, "reset_time": time.time() + 3600})
        
        # Enhanced artist database
        self.popular_artists = [
            "zekefox", "aurorafox", "dogear", "reynardf", "kyander", "wolfy-nail", 
            "twinkle-sez", "miles-df", "rajii", "tokifuji", "slugbox", "diives",
            "whisperingfornothing", "drako1997", "jishinu", "cervina7", "yasmil",
            "tojo_the_thief", "sirphilliam", "hioshiru", "chelodoy", "oouna"
        ]
        
        self.banned_tags = [
            "cub", "shota", "loli", "gore", "scat", "watersports", "vore", 
            "snuff", "necrophilia", "bestiality", "rape", "abuse", "torture"
        ]

    async def cog_load(self):
        """Initialize when cog is loaded"""
        # Type ignore due to discord.py dynamic attribute
        if not hasattr(self, 'cleanup_cache') or not self.cleanup_cache.is_running():  # type: ignore[attr-defined]
            self.cleanup_cache.start()  # type: ignore[attr-defined]

    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        if hasattr(self, 'cleanup_cache') and self.cleanup_cache.is_running():  # type: ignore[attr-defined]
            self.cleanup_cache.cancel()  # type: ignore[attr-defined]

    @tasks.loop(hours=1)
    async def cleanup_cache(self):
        """Clean up expired cache entries"""
        try:
            current_time = time.time()
            expired_keys = [
                key for key, timestamp in self.cache.timestamps.items()
                if current_time - timestamp > self.cache.ttl
            ]
            for key in expired_keys:
                if key in self.cache.cache:
                    del self.cache.cache[key]
                if key in self.cache.timestamps:
                    del self.cache.timestamps[key]
        except Exception as e:
            logging.error(f"Cache cleanup error: {e}")

    @cleanup_cache.before_loop  # type: ignore[attr-defined]
    async def before_cleanup_cache(self):
        await self.bot.wait_until_ready()

    def is_rate_limited(self, user_id: int) -> bool:
        """Check if user is rate limited"""
        try:
            user_limits = self.rate_limits[user_id]
            if time.time() > user_limits["reset_time"]:
                user_limits["count"] = 0
                user_limits["reset_time"] = time.time() + 3600
            
            if user_limits["count"] >= 100:  # 100 requests per hour
                return True
            
            user_limits["count"] += 1
            return False
        except Exception:
            return False

    async def fetch_valid_posts(self, query: str, limit: int = 25) -> List[Dict]:
        """Enhanced post fetching with caching and better filtering"""
        try:
            # Encode query safely for URL (spaces -> +, special chars encoded)
            encoded_query = quote_plus(query.strip())
            cache_key = f"{encoded_query}_{limit}"
            cached_posts = self.cache.get(cache_key)
            if cached_posts:
                return cached_posts

            url = f"https://e621.net/posts.json?tags={encoded_query}&limit={limit}"
            if not E621_USERNAME or not E621_API_KEY:
                logging.warning("E621 credentials missing.")
                return []

            auth_string = f"{E621_USERNAME}:{E621_API_KEY}"
            encoded_auth = base64.b64encode(auth_string.encode()).decode()
            headers = {
                "User-Agent": f"BringusBot/9.6.3 (by {E621_USERNAME} on e621)",
                "Authorization": f"Basic {encoded_auth}"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=30) as resp:
                    if resp.status == 429:  # Rate limited
                        await asyncio.sleep(1)
                        return []
                    elif resp.status != 200:
                        logging.warning(f"e621 fetch failed: {resp.status}")
                        return []
                    
                    data = await resp.json()
                    posts = data.get("posts", [])
                    
                    # Enhanced filtering
                    valid_posts = []
                    for post in posts:
                        try:
                            file_info = post.get("file", {})
                            file_url = file_info.get("url", "")
                            
                            # Check if it's a valid image/gif
                            if file_url and file_url.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                                # Check file size (skip very large files)
                                file_size = file_info.get("size", 0)
                                if file_size < 25 * 1024 * 1024:  # 25MB limit
                                    valid_posts.append(post)
                        except Exception as e:
                            logging.warning(f"Error processing post: {e}")
                            continue
                    
                    # Cache the results
                    self.cache.set(cache_key, valid_posts)
                    return valid_posts
        except Exception as e:
            logging.error(f"Fetch error: {e}")
            return []

    def create_post_embed(self, post: Dict, current: int = 1, total: int = 1) -> discord.Embed:
        """Create enhanced embed for e621 post"""
        try:
            file_info = post.get('file', {})
            file_url = file_info.get('url', '')
            
            if not file_url:
                raise ValueError("No file URL found")
            
            rating = post.get("rating", "u")
            score = post.get("score", {})
            score_total = score.get("total", 0) if isinstance(score, dict) else 0
            fav_count = post.get("fav_count", 0)
            
            # Get tags by category
            tags = post.get("tags", {})
            artists = tags.get("artist", []) if isinstance(tags, dict) else []
            species = tags.get("species", []) if isinstance(tags, dict) else []
            general = tags.get("general", []) if isinstance(tags, dict) else []
            
            # Rating emoji (safe = ✅ instead of NSFW indicator)
            rating_emoji = {"s": "✅", "q": "⚠️", "e": "🔞"}.get(rating, "❓")
            
            embed = discord.Embed(
                title=f"{rating_emoji} e621 Post #{post.get('id', 'Unknown')} ({current}/{total})",
                url=f"https://e621.net/posts/{post.get('id', 0)}",
                color=discord.Color.purple()
            )
            
            # Add detailed information
            if artists:
                embed.add_field(name="🎨 Artist(s)", value=", ".join(artists[:3]), inline=True)
            if species:
                embed.add_field(name="🐾 Species", value=", ".join(species[:3]), inline=True)
            
            embed.add_field(name="📊 Stats", value=f"👍 {score_total} | ⭐ {fav_count}", inline=True)
            
            if general:
                tag_text = ", ".join(general[:8])
                if len(tag_text) > 100:
                    tag_text = tag_text[:97] + "..."
                embed.add_field(name="🏷️ Tags", value=tag_text, inline=False)
            
            embed.set_image(url=file_url)
            created_at = post.get('created_at', 'Unknown')
            if isinstance(created_at, str) and len(created_at) >= 10:
                created_at = created_at[:10]
            else:
                created_at = 'Unknown'
            embed.set_footer(text=f"Rating: {rating.upper()} | Posted: {created_at}")
            
            return embed
        except Exception as e:
            logging.error(f"Error creating embed: {e}")
            # Return a simple error embed
            return discord.Embed(
                title="❌ Error",
                description="Failed to load post information",
                color=discord.Color.red()
            )

    def create_detailed_info_embed(self, post: Dict) -> discord.Embed:
        """Create detailed information embed for a post"""
        try:
            embed = discord.Embed(
                title=f"📋 Detailed Info - Post #{post.get('id', 'Unknown')}",
                url=f"https://e621.net/posts/{post.get('id', 0)}",
                color=discord.Color.blue()
            )
            
            # File information
            file_info = post.get("file", {})
            file_size = file_info.get('size', 0)
            file_size_kb = file_size // 1024 if file_size else 0
            
            embed.add_field(
                name="📁 File Info",
                value=f"Size: {file_size_kb}KB\n"
                      f"Format: {file_info.get('ext', 'unknown').upper()}\n"
                      f"Dimensions: {file_info.get('width', '?')}x{file_info.get('height', '?')}",
                inline=True
            )
            
            # Post stats
            score = post.get("score", {})
            if isinstance(score, dict):
                score_total = score.get('total', 0)
                score_up = score.get('up', 0)
                score_down = score.get('down', 0)
            else:
                score_total = score_up = score_down = 0
                
            embed.add_field(
                name="📊 Statistics",
                value=f"Score: {score_total} (+{score_up}/-{score_down})\n"
                      f"Favorites: {post.get('fav_count', 0)}\n"
                      f"Comments: {post.get('comment_count', 0)}",
                inline=True
            )
            
            # Dates
            created = post.get("created_at", "")
            updated = post.get("updated_at", "")
            created_date = created[:10] if isinstance(created, str) and len(created) >= 10 else "Unknown"
            updated_date = updated[:10] if isinstance(updated, str) and len(updated) >= 10 else "Unknown"
            
            embed.add_field(
                name="📅 Dates",
                value=f"Created: {created_date}\nUpdated: {updated_date}",
                inline=True
            )
            
            # All tags
            tags = post.get("tags", {})
            if isinstance(tags, dict):
                for category, tag_list in tags.items():
                    if tag_list and category != "invalid" and isinstance(tag_list, list):
                        tag_text = ", ".join(tag_list[:10])
                        if len(tag_text) > 200:
                            tag_text = tag_text[:197] + "..."
                        embed.add_field(name=f"🏷️ {category.title()}", value=tag_text, inline=False)
            
            return embed
        except Exception as e:
            logging.error(f"Error creating detailed embed: {e}")
            return discord.Embed(
                title="❌ Error",
                description="Failed to load detailed information",
                color=discord.Color.red()
            )

    async def get_ai_comment(self, tags: List[str]) -> Optional[str]:
        """Get AI comment about the tags"""
        if not OPENAI_API_KEY:
            return None
        if not tags:
            return None  # Nothing to comment on
        
        try:
            try:
                import openai  # Local import to avoid mandatory dependency
            except ImportError:
                logging.warning("openai package not installed; skipping AI comment.")
                return None
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            # Run blocking call in executor to avoid blocking event loop
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You're Fluxy, a mischievous and flirty furry bot with a playful personality. React to e621 tags with cheeky humor, innuendo, and furry culture references. Be suggestive but not explicit. Use uwu speech occasionally. Keep responses under 100 characters and full of personality!"},
                        {"role": "user", "content": f"React to these tags: {', '.join(tags[:8])}"}
                    ],
                    max_tokens=50,
                    temperature=0.9
                )
            )
            content = getattr(response.choices[0].message, 'content', None)
            return content.strip() if content else None
        except Exception as e:
            logging.error(f"OpenAI error: {e}")
            return None

    @app_commands.command(name="e621", description="NSFW image search from e621.net with enhanced features")
    @app_commands.describe(query="Tags or artist, e.g. artist:zekefox or canine")
    async def e621(self, interaction: discord.Interaction, query: str):
        try:
            # NSFW channel check
            channel = interaction.channel
            if not (isinstance(channel, discord.TextChannel) and channel.is_nsfw()):
                await interaction.response.send_message("🚫 This command only works in NSFW channels.", ephemeral=True)
                return

            # Rate limiting
            if self.is_rate_limited(interaction.user.id):
                await interaction.response.send_message("⏰ You're being rate limited. Please wait before searching again.", ephemeral=True)
                return

            # User daily limit
            if self.user_stats.is_rate_limited(interaction.user.id):
                await interaction.response.send_message("📊 You've reached your daily search limit (50). Try again tomorrow!", ephemeral=True)
                return

            # Banned tags check (token-based to avoid partial word false positives)
            lowered = query.lower()
            tokens = set(re.split(r'[\s]+', lowered))
            if any(tag in tokens for tag in self.banned_tags):
                await interaction.response.send_message("❌ That tag is blocked for safety reasons.", ephemeral=True)
                return

            # Clean and validate query - allow alphanumerics, underscore, colon, dash and space
            query = re.sub(r'[^\w\s:.-]', '', query).strip()
            if len(query) > 100:
                query = query[:100]
            
            if not query:
                await interaction.response.send_message("❌ Invalid search query.", ephemeral=True)
                return

            view = NSFWConfirmView(self, query)
            await interaction.response.send_message("🔞 Confirm to view NSFW search results:", view=view, ephemeral=True)
        except Exception as e:
            logging.error(f"E621 command error: {e}")
            try:
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)
            except:
                pass

    async def send_results(self, interaction: discord.Interaction, query: str):
        """Send enhanced search results with navigation"""
        try:
            await interaction.followup.send("📡 Searching e621...", ephemeral=True)
            posts = await self.fetch_valid_posts(query, 50)  # Get more posts for navigation

            if not posts:
                suggestions = await self.get_search_suggestions(query)
                suggestion_text = f"\n\n💡 **Suggestions:** {', '.join(suggestions)}" if suggestions else ""
                await interaction.followup.send(f"😿 No results found for `{query}`.{suggestion_text}", ephemeral=True)
                return

            # Create initial embed and view
            embed = self.create_post_embed(posts[0], 1, len(posts))
            view = E621PostView(self, posts)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

            # Update user statistics
            first_post = posts[0]
            all_tags = []
            tags = first_post.get("tags", {})
            if isinstance(tags, dict):
                for tag_list in tags.values():
                    if isinstance(tag_list, list):
                        all_tags.extend(tag_list)
            # Deduplicate while preserving order
            seen = set()
            all_tags = [t for t in all_tags if not (t in seen or seen.add(t))]
            self.user_stats.add_search(interaction.user.id, query, all_tags)

            # AI comment
            if os.getenv("ENABLE_FLUXY_COMMENTS") == "1":
                ai_comment = await self.get_ai_comment(all_tags[:8])
                if ai_comment:
                    await asyncio.sleep(2)  # Slight delay for effect
                    await interaction.followup.send(f"🦊 **Fluxy says:** *{ai_comment}*", ephemeral=True)

            # Modlog
            if MODLOG_CHANNEL_ID:
                log_channel = self.bot.get_channel(MODLOG_CHANNEL_ID)
                if log_channel:
                    await log_channel.send(
                        f"🔍 `{interaction.user}` searched e621: `{query}` | Results: {len(posts)}"
                    )
        except Exception as e:
            logging.error(f"Send results error: {e}")
            try:
                await interaction.followup.send("❌ An error occurred while fetching results.", ephemeral=True)
            except:
                pass

    async def get_search_suggestions(self, query: str) -> List[str]:
        """Get search suggestions based on failed query"""
        try:
            suggestions = []
            
            # Common misspellings and alternatives
            corrections = {
                "fox": ["canine", "vulpine", "kitsune"],
                "wolf": ["canine", "lupine", "werewolf"],
                "cat": ["feline", "domestic_cat", "kitten"],
                "dog": ["canine", "domestic_dog", "puppy"],
                "dragon": ["scalie", "western_dragon", "eastern_dragon"]
            }
            
            for word, alts in corrections.items():
                if re.search(rf"\b{re.escape(word)}\b", query.lower()):
                    suggestions.extend(alts)
            
            # Add popular tags
            if not suggestions:
                suggestions = ["anthro", "solo", "male", "female", "fur"]
            
            return suggestions[:3]
        except Exception:
            return ["anthro", "solo", "fur"]

    @app_commands.command(name="e621stats", description="View your e621 search statistics")
    async def e621stats(self, interaction: discord.Interaction):
        try:
            user_id = interaction.user.id
            stats = self.user_stats.user_data[user_id]
            
            embed = discord.Embed(
                title="📊 Your e621 Statistics",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="🔢 Search Count",
                value=f"Total: {stats['searches']}\nToday: {stats['daily_searches']}",
                inline=True
            )
            
            # Top tags
            top_tags = self.user_stats.get_top_tags(user_id)
            if top_tags:
                tag_text = "\n".join([f"{tag}: {count}x" for tag, count in top_tags])
                embed.add_field(name="🏷️ Favorite Tags", value=tag_text, inline=True)
            
            # Last search
            if stats['last_search']:
                embed.add_field(
                    name="🕐 Last Search", 
                    value=f"<t:{int(stats['last_search'].timestamp())}:R>", 
                    inline=True
                )
            
            # Recent searches
            if stats['search_history']:
                recent = stats['search_history'][-3:]
                recent_text = "\n".join([f"`{search['query']}`" for search in reversed(recent)])
                embed.add_field(name="🔍 Recent Searches", value=recent_text, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logging.error(f"Stats command error: {e}")
            await interaction.response.send_message("❌ Error loading statistics.", ephemeral=True)

    @app_commands.command(name="randomartist", description="Pick a random furry artist with enhanced recommendations")
    async def randomartist(self, interaction: discord.Interaction):
        try:
            user_id = interaction.user.id
            
            # Get user's favorite tags to suggest similar artists
            top_tags = self.user_stats.get_top_tags(user_id, 10)
            
            # Select artist
            artist = random.choice(self.popular_artists)
            
            embed = discord.Embed(
                title="🎨 Random Artist Recommendation",
                description=f"**{artist}**",
                color=discord.Color.gold()
            )
            
            embed.add_field(
                name="🔍 Try searching:",
                value=f"`/e621 artist:{artist}`",
                inline=False
            )
            
            if top_tags:
                # Suggest combining with user's favorite tags
                fav_tag = top_tags[0][0]
                embed.add_field(
                    name="💡 Personalized suggestion:",
                    value=f"`/e621 artist:{artist} {fav_tag}`",
                    inline=False
                )
            
            embed.set_footer(text=f"Artist {self.popular_artists.index(artist) + 1} of {len(self.popular_artists)}")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logging.error(f"Random artist error: {e}")
            await interaction.response.send_message("❌ Error getting random artist.", ephemeral=True)

    @app_commands.command(name="e621help", description="Get help with e621 search syntax and features")
    async def e621help(self, interaction: discord.Interaction):
        try:
            embed = discord.Embed(
                title="📚 e621 Search Help",
                description="Learn how to search effectively on e621!",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="🔍 Basic Syntax",
                value="• `tag1 tag2` - Posts with both tags\n"
                      "• `tag1 ~tag2` - Posts with either tag\n"
                      "• `-tag` - Exclude a tag\n"
                      "• `artist:name` - Specific artist",
                inline=False
            )
            
            embed.add_field(
                name="🎯 Examples",
                value="• `fox solo` - Solo fox characters\n"
                      "• `artist:zekefox` - Posts by ZekeFox\n"
                      "• `canine -cub` - Canines excluding cubs\n"
                      "• `dragon ~western_dragon ~eastern_dragon` - Any dragon type",
                inline=False
            )
            
            embed.add_field(
                name="⚡ Bot Features",
                value="• Navigation buttons for multiple results\n"
                      "• Detailed post information\n"
                      "• Personal statistics tracking\n"
                      "• AI-powered reactions (Fluxy mode)",
                inline=False
            )
            
            embed.add_field(
                name="🚫 Blocked Tags",
                value="Certain tags are blocked for safety.\nUse `/e621stats` to view your search history.",
                inline=False
            )
            
            embed.set_footer(text="Visit e621.net for the full tag database")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logging.error(f"Help command error: {e}")
            await interaction.response.send_message("❌ Error loading help.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(E621(bot))