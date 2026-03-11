import os
import re
import time
from typing import Dict, List, Optional

import aiohttp
import discord
from discord.ext import commands
from openai import AsyncOpenAI

from utils.db import get_user_mood
from utils.memory import clear_memory, get_memory, update_memory
from utils.personality_router import get_persona_prompt


# ==========================
# Easy-to-tune configuration
# ==========================

PERSONA_NAME = "fluxy"
DEFAULT_MOOD = "friendly"

USER_COOLDOWN_SECONDS = 15
GLOBAL_COOLDOWN_SECONDS = 3

# If enabled, Fluxy replies with a short message during cooldown.
# Rate-limited to avoid spamming the channel when someone is mention-spamming.
COOLDOWN_FEEDBACK_ENABLED = True
COOLDOWN_FEEDBACK_PER_USER_SECONDS = 30

MENTION_ENABLED = True
REPLY_WITH_THREADS = True
MAX_MEMORY_LINES = 10

# Recent channel context (makes replies feel less random)
RECENT_CONTEXT_ENABLED = True
RECENT_CONTEXT_MESSAGES = 8
RECENT_CONTEXT_PER_LINE_CHARS = 140
RECENT_CONTEXT_TOTAL_CHARS = 900

# Natural-language controls (no slash commands)
ALLOW_MEMORY_RESET_PHRASES = True
ALLOW_HELP_PHRASES = True

DISCORD_MAX_CHARS = 2000
REPLY_HEADROOM = 50
MAX_REPLY_CHARS = DISCORD_MAX_CHARS - REPLY_HEADROOM

# Safety: keep prompts from ballooning due to spam/huge pastes.
MAX_USER_INPUT_CHARS = 1200
MAX_MEMORY_LINE_CHARS = 400
MAX_SAVED_REPLY_CHARS = 800

# Steam
STEAM_ENABLED = True
STEAM_CC = "us"
STEAM_LANG = "en"

# Weather
WEATHER_ENABLED = True
WEATHER_API_KEY_ENV = "OPENWEATHER_API_KEY"
WEATHER_UNITS = "metric"

# OpenAI
OPENAI_MODEL = "gpt-4o"
TEMPERATURE = 0.85
MAX_TOKENS = 550

EXTRA_SYSTEM_INSTRUCTIONS = (
    "You are Fluxy, a confident, funny, chronically-online gamer friend hanging out in a Discord server. "
    "You give strong opinions, quick takes, and casual recommendations. "
    "Blend what's popular right now with all-time classics naturally. "
    "Match the user's energy (chaotic, chill, serious, funny). "
    "Never mention knowledge cutoffs, training data, or limitations. "
    "Never say you are an AI. "
    "Use light emojis and keep replies readable."
)

THREAD_NAME_TEMPLATE = "{username} × Fluxy 🎮"


# ==================
# Helper data models
# ==================

class SteamGame:
    def __init__(self, name: str, price: Optional[str], discount: Optional[int], url: str):
        self.name = name
        self.price = price
        self.discount = discount
        self.url = url

    def line(self) -> str:
        parts = [self.name]
        if self.discount:
            parts.append(f"-{self.discount}%")
        if self.price:
            parts.append(self.price)
        parts.append(self.url)
        return " • ".join(parts)


class WeatherSnapshot:
    def __init__(self, location: str, description: str, temp: float, feels_like: float):
        self.location = location
        self.description = description
        self.temp = temp
        self.feels_like = feels_like

    def line(self) -> str:
        return f"{self.location}: {self.description}, {self.temp:.1f}° (feels {self.feels_like:.1f}°)"


# ===============
# Cog definition
# ===============

class FluxyMention(commands.Cog):
    """Mention-based gamer friend bot with Steam + Weather awareness."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        self._user_last_used: Dict[int, float] = {}
        self._last_global_use: float = 0.0

        # user_id -> last time we emitted a cooldown notice (monotonic)
        self._user_last_cooldown_notice: Dict[int, float] = {}

        self._user_locations: Dict[int, str] = {}
        self._awaiting_location: Dict[int, bool] = {}

    # ----------------
    # Core listener
    # ----------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not MENTION_ENABLED:
            return

        should_respond = await self._should_respond(message)
        if not should_respond:
            return

        cooldown = self._check_cooldowns(message.author.id)
        if cooldown:
            if COOLDOWN_FEEDBACK_ENABLED:
                now_m = time.monotonic()
                last_notice = self._user_last_cooldown_notice.get(message.author.id, 0.0)
                if now_m - last_notice >= COOLDOWN_FEEDBACK_PER_USER_SECONDS:
                    self._user_last_cooldown_notice[message.author.id] = now_m
                    await message.reply(cooldown, mention_author=False)
            return

        self._mark_used(message.author.id)

        clean_text = self._clean_content(message)
        if not clean_text:
            clean_text = "Say something fun."

        if len(clean_text) > MAX_USER_INPUT_CHARS:
            clean_text = clean_text[: MAX_USER_INPUT_CHARS - 1] + "…"

        text_lower = clean_text.lower()

        if ALLOW_HELP_PHRASES and any(k in text_lower for k in ("help", "what can you do", "how do i use")):
            await message.reply(self._help_text(), mention_author=False)
            return

        if ALLOW_MEMORY_RESET_PHRASES and any(
            k in text_lower
            for k in (
                "reset memory",
                "forget me",
                "forget that",
                "wipe memory",
                "clear memory",
            )
        ):
            cleared = clear_memory(message.author.id)
            await message.reply(
                "Done — wiped what I remembered about you." if cleared else "I didn’t have anything saved for you yet.",
                mention_author=False,
            )
            return

        is_steam = STEAM_ENABLED and "steam" in text_lower
        is_weather = WEATHER_ENABLED and any(
            k in text_lower for k in ("weather", "rain", "snow", "hot", "cold", "forecast", "temp")
        )

        # If we asked for a location, treat the next message as location input (even if it includes "weather").
        if self._awaiting_location.get(message.author.id):
            self._user_locations[message.author.id] = clean_text
            self._awaiting_location.pop(message.author.id, None)
            await message.reply(f"Got it — saved **{clean_text}** 🌍", mention_author=False)
            return

        if is_weather and message.author.id not in self._user_locations:
            if not self._awaiting_location.get(message.author.id):
                self._awaiting_location[message.author.id] = True
                await message.reply(
                    "Weather check? Drop your city once and I’ll remember 👀",
                    mention_author=False,
                )
            return

        steam_data = None
        weather_data = None
        recent_context = None

        async with message.channel.typing():
            if RECENT_CONTEXT_ENABLED:
                recent_context = await self._get_recent_context(message)

            if is_steam:
                steam_data = await self._fetch_steam()
            if is_weather:
                loc = self._user_locations.get(message.author.id)
                if loc:
                    weather_data = await self._fetch_weather(loc)

            mood = get_user_mood(message.author.id, DEFAULT_MOOD)
            reply = await self._generate_reply(
                message.author.id,
                message.author.display_name,
                clean_text,
                mood,
                steam_data,
                weather_data,
                recent_context,
            )

            update_memory(message.author.id, self._truncate_for_memory(f"User: {clean_text}", MAX_MEMORY_LINE_CHARS))
            update_memory(message.author.id, self._truncate_for_memory(f"Fluxy: {reply}", MAX_SAVED_REPLY_CHARS))

            await self._send_reply(message, reply, mood)

    # ----------------
    # Cooldowns
    # ----------------

    def _check_cooldowns(self, user_id: int) -> Optional[str]:
        now = time.monotonic()

        if now - self._last_global_use < GLOBAL_COOLDOWN_SECONDS:
            return "Hold up a sec 😅"

        last = self._user_last_used.get(user_id, 0.0)
        if now - last < USER_COOLDOWN_SECONDS:
            return "Give me a moment, speedrunner."

        return None

    def _mark_used(self, user_id: int):
        now = time.monotonic()
        self._user_last_used[user_id] = now
        self._last_global_use = now

    @staticmethod
    def _truncate_for_memory(text: str, limit: int) -> str:
        if limit <= 0:
            return ""
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)] + "…"

    # ----------------
    # Utilities
    # ----------------

    def _clean_content(self, message: discord.Message) -> str:
        content = message.content or ""
        if self.bot.user:
            content = re.sub(rf"<@!?{self.bot.user.id}>", "", content)
        return re.sub(r"\s+", " ", content).strip()

    async def _should_respond(self, message: discord.Message) -> bool:
        if self.bot.user is None:
            return False

        # Normal: mention-based trigger.
        if self.bot.user in message.mentions:
            return True

        # Helpful: if the user replies directly to Fluxy's message, continue the convo.
        ref = message.reference
        if not ref:
            return False

        resolved = getattr(ref, "resolved", None)
        if isinstance(resolved, discord.Message):
            return resolved.author.id == self.bot.user.id

        # If not resolved (cache miss), do not fetch (keeps it cheap).
        return False

    def _help_text(self) -> str:
        parts = [
            "Mention me with a question and I’ll answer.",
            "You can say **reset memory** / **clear memory** if you want me to forget our saved context.",
        ]
        if STEAM_ENABLED:
            parts.append("Say **steam** to pull a quick Steam specials snapshot.")
        if WEATHER_ENABLED:
            parts.append("Say **weather** (I’ll ask for your city once).")
        return "\n".join(parts)

    # ----------------
    # Steam
    # ----------------

    async def _fetch_steam(self) -> Optional[List[SteamGame]]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://store.steampowered.com/api/featuredcategories/",
                    params={"cc": STEAM_CC, "l": STEAM_LANG},
                    timeout=10,
                ) as resp:
                    data = await resp.json()
                    items = data.get("specials", {}).get("items", [])[:5]
                    games = []
                    for it in items:
                        price = f"${it['final_price'] / 100:.2f}" if it.get("final_price") else None
                        games.append(
                            SteamGame(
                                it.get("name", "Unknown"),
                                price,
                                it.get("discount_percent"),
                                f"https://store.steampowered.com/app/{it.get('id')}",
                            )
                        )
                    return games
        except Exception as e:
            print(f"[Fluxy] Steam error: {e}")
            return None

    # ----------------
    # Weather
    # ----------------

    async def _fetch_weather(self, location: str) -> Optional[WeatherSnapshot]:
        api_key = os.getenv(WEATHER_API_KEY_ENV)
        if not api_key:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"q": location, "appid": api_key, "units": WEATHER_UNITS},
                    timeout=10,
                ) as resp:
                    data = await resp.json()
                    main = data["main"]
                    desc = data["weather"][0]["description"]
                    return WeatherSnapshot(
                        data.get("name", location),
                        desc,
                        float(main["temp"]),
                        float(main["feels_like"]),
                    )
        except Exception as e:
            print(f"[Fluxy] Weather error: {e}")
            return None

    # ----------------
    # AI
    # ----------------

    async def _generate_reply(
        self,
        user_id: int,
        username: str,
        content: str,
        mood: str,
        steam: Optional[List[SteamGame]],
        weather: Optional[WeatherSnapshot],
        recent_context: Optional[str],
    ) -> str:
        system = get_persona_prompt(PERSONA_NAME, mood) + "\n\n" + EXTRA_SYSTEM_INSTRUCTIONS

        mem_lines = [self._truncate_for_memory(s, MAX_MEMORY_LINE_CHARS) for s in get_memory(user_id)[-MAX_MEMORY_LINES:]]
        memory = "\n".join(mem_lines)

        context = []
        if steam:
            context.append("Steam snapshot:")
            context.extend(f"- {g.line()}" for g in steam)
        if weather:
            context.append(f"Weather snapshot:\n- {weather.line()}")
        if recent_context:
            context.append(recent_context)

        user_prompt = "\n\n".join(
            filter(
                None,
                [
                    memory,
                    "\n".join(context),
                    f"{username} said:",
                    content,
                ],
            )
        )

        # Extra safety: cap final prompt size too (context + memory can add up).
        if len(user_prompt) > 6000:
            user_prompt = user_prompt[-6000:]

        try:
            if not os.getenv("OPENAI_API_KEY"):
                return "I can’t think right now — my OpenAI key isn’t set on the server."

            res = await self.openai.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
            )
            reply_content: Optional[str] = res.choices[0].message.content
            if reply_content is None:
                return "Something glitched — try again in a sec."
            return reply_content.strip()
        except Exception as e:
            print(f"[Fluxy] OpenAI error: {e}")
            return "Something glitched — try again in a sec."

    # ----------------
    # Reply
    # ----------------

    async def _send_reply(self, message: discord.Message, text: str, mood: str):
        chunks = self._chunk(text, MAX_REPLY_CHARS)
        reply = await message.reply(chunks[0], mention_author=False)

        for extra in chunks[1:]:
            await reply.channel.send(extra)

        # Create threads only when useful (e.g., long multi-part replies) to reduce channel spam.
        should_thread = REPLY_WITH_THREADS and len(chunks) > 1
        if should_thread and not isinstance(message.channel, discord.Thread):
            try:
                await reply.create_thread(
                    name=THREAD_NAME_TEMPLATE.format(username=message.author.display_name),
                    auto_archive_duration=60,
                )
            except discord.HTTPException:
                pass

    async def _get_recent_context(self, message: discord.Message) -> Optional[str]:
        # If history isn't accessible, just skip.
        channel = message.channel
        if not hasattr(channel, "history"):
            return None

        lines: List[str] = []
        total = 0

        try:
            async for m in channel.history(limit=RECENT_CONTEXT_MESSAGES, before=message):
                if m.author.bot:
                    continue
                if not m.content:
                    continue

                content = re.sub(r"\s+", " ", m.content).strip()
                if not content:
                    continue

                # Drop obvious command-like lines to reduce noise.
                if content.startswith("/") or content.startswith("!"):
                    continue

                if len(content) > RECENT_CONTEXT_PER_LINE_CHARS:
                    content = content[: RECENT_CONTEXT_PER_LINE_CHARS - 1] + "…"

                line = f"{m.author.display_name}: {content}"
                if total + len(line) + 1 > RECENT_CONTEXT_TOTAL_CHARS:
                    break
                lines.append(line)
                total += len(line) + 1
        except (discord.Forbidden, discord.HTTPException):
            return None

        if not lines:
            return None

        lines.reverse()  # oldest -> newest
        return "Recent chat context (oldest→newest):\n" + "\n".join(f"- {l}" for l in lines)

    @staticmethod
    def _chunk(text: str, limit: int) -> List[str]:
        return [text[i:i + limit] for i in range(0, len(text), limit)]


async def setup(bot: commands.Bot):
    await bot.add_cog(FluxyMention(bot))