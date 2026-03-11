import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
from collections import defaultdict
import datetime
import json
import os
import asyncio
from typing import Optional, Dict, List, Tuple, Any
import logging
from asyncio import Lock
import time

from utils.counting_config import (
    DIFFICULTY_PROFILES,
    MURKOFF_BRIEFINGS,
    MURKOFF_CODENAMES,
    MURKOFF_DISSOCIATION_LINES,
    MURKOFF_MESSAGES,
    MURKOFF_PARANOIA_LINES,
    MURKOFF_POSTERS,
    get_murkoff_line,
    load_special_numbers,
)
class CountingData:
    """Handles data persistence for counting game"""
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.ensure_data_directory()
    
    def ensure_data_directory(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def load_guild_data(self, guild_id: int) -> dict:
        """Load counting data for a specific guild"""
        file_path = os.path.join(self.data_dir, f"counting_{guild_id}.json")
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            # Countdown event state (passive / unused for now). Backfill safely for older saves.
            data.setdefault("countdown_active", False)
            data.setdefault("countdown_user_id", None)
            data.setdefault("countdown_expires_at", None)

            # Cosmetic psychotic state tracking (passive / unused for now). Backfill safely for older saves.
            data.setdefault("psychotic_active", None)
            data.setdefault("psychotic_expires_at", None)
            data.setdefault("psychotic_announced_active", None)

            # Red Light / Green Light event state (passive / unused for now). Backfill safely for older saves.
            data.setdefault("rlgl_active", False)
            data.setdefault("rlgl_state", None)  # Optional[str]: "red" or "green"
            data.setdefault("rlgl_expires_at", None)  # Optional[float]: epoch seconds

            # Theme state tracking (passive / unused for now). Backfill safely for older saves.
            data.setdefault("active_theme", None)  # Optional[str] e.g. "permafrost", "blackout"
            data.setdefault("theme_started_at", None)  # Optional[float]: epoch seconds
            return data
        except (FileNotFoundError, json.JSONDecodeError):
            return self.get_default_guild_data()
    
    def save_guild_data(self, guild_id: int, data: dict):
        """Save counting data for a specific guild"""
        file_path = os.path.join(self.data_dir, f"counting_{guild_id}.json")
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logging.error(f"Failed to save guild data for {guild_id}: {e}")
    
    def get_default_guild_data(self) -> dict:
        """Get default guild data structure"""
        return {
            "current_number": 1,
            # Flavor-only: tracks escalation phase announcements to avoid repeats.
            "last_phase": 0,
            # Countdown event state (passive / unused for now).
            "countdown_active": False,
            "countdown_user_id": None,
            "countdown_expires_at": None,

            # Red Light / Green Light event state (passive / unused for now).
            "rlgl_active": False,
            "rlgl_state": None,  # Optional[str]: "red" or "green"
            "rlgl_expires_at": None,  # Optional[float]: epoch seconds

            # Theme state tracking (passive / unused for now).
            "active_theme": None,  # Optional[str] e.g. "permafrost", "blackout"
            "theme_started_at": None,  # Optional[float]: epoch seconds

            # Cosmetic psychotic state tracking (passive / unused for now).
            # Optional[str] (e.g. "paranoia", "dissociation", "dejavu")
            "psychotic_active": None,
            # Optional[float] (epoch seconds)
            "psychotic_expires_at": None,
            # Tracks whether we already announced the current psychotic.
            "psychotic_announced_active": None,
            "lives": 3,
            "last_user_id": None,
            "channel_id": None,
            "count_stats": {},
            "failures": 0,
            "last_fail_user": None,
            "last_reset": datetime.datetime.utcnow().isoformat(),
            "streaks": {},
            "highest_streak": 0,
            "highest_streak_user": None,
            "bringushell_mode": False,
            "difficulty_mode": "normal",
            "achievements": {},
            "milestones": [],
            "daily_stats": {},
            "weekly_stats": {},
            "monthly_stats": {},
            "last_count_timestamp": None,  # New optional field
            # Daily target mini-game: hit numbers ending with this digit today to claim a star
            "daily_target": {"date": None, "last_digit": None, "winner_user_id": None},
            # Difficulty controls
            "difficulty_scope": "global",  # "global" or "per-user"
            "user_difficulties": {},  # { user_id: mode }
        }

class CountingAchievements:
    """Handles achievement system for counting game"""
    
    ACHIEVEMENTS = {
        "first_count": {"name": "First Steps", "description": "Count your first number", "emoji": "👶"},
        "streak_5": {"name": "Streak Starter", "description": "Get a 5-count streak", "emoji": "🔥"},
        "streak_10": {"name": "On Fire", "description": "Get a 10-count streak", "emoji": "🌟"},
        "streak_25": {"name": "Unstoppable", "description": "Get a 25-count streak", "emoji": "⚡"},
        "streak_50": {"name": "Legendary", "description": "Get a 50-count streak", "emoji": "👑"},
        "streak_100": {"name": "Demigod", "description": "Get a 100-count streak", "emoji": "🛡️"},
        
        "count_10": {"name": "Getting Started", "description": "Participate in 10 counts", "emoji": "🪙"},
        "count_100": {"name": "Century Club", "description": "Participate in 100 counts", "emoji": "💯"},
        "count_250": {"name": "Quarter Way", "description": "Participate in 250 counts", "emoji": "🧭"},
        "count_500": {"name": "Dedicated Counter", "description": "Participate in 500 counts", "emoji": "🎯"},
        "count_1000": {"name": "Master Counter", "description": "Participate in 1000 counts", "emoji": "🏆"},
        "count_2500": {"name": "Elite Counter", "description": "Participate in 2500 counts", "emoji": "💠"},
        "count_5000": {"name": "Mythic Counter", "description": "Participate in 5000 counts", "emoji": "🐉"},
        "count_10000": {"name": "Counting God", "description": "Participate in 10000 counts", "emoji": "⚡"},
        
        "milestone_100": {"name": "First Milestone", "description": "Reach number 100", "emoji": "🎖️"},
        "milestone_420": {"name": "Blaze It", "description": "Reach number 420", "emoji": "🔥"},
        "milestone_500": {"name": "Big Milestone", "description": "Reach number 500", "emoji": "🏅"},
        "milestone_1000": {"name": "Epic Milestone", "description": "Reach number 1000", "emoji": "🥇"},
        "milestone_1337": {"name": "Leet", "description": "Reach number 1337", "emoji": "🕶️"},
        "milestone_5000": {"name": "Titan", "description": "Reach number 5000", "emoji": "🌌"},
        "milestone_10000": {"name": "Ascended", "description": "Reach number 10000", "emoji": "🚀"},
        
        "fail_recovery": {"name": "Phoenix", "description": "Recover after losing all lives", "emoji": "🔄"},
        "perfect_day": {"name": "Perfect Day", "description": "Count 50 numbers without failing", "emoji": "✨"},
        "night_owl": {"name": "Night Owl", "description": "Count between 2-6 AM", "emoji": "🦉"},
        "early_bird": {"name": "Early Bird", "description": "Count between 5-8 AM", "emoji": "🐦"},
        "speed_demon": {"name": "Speed Demon", "description": "Count within 10 seconds of previous", "emoji": "💨"},
        # New pattern and event achievements
        "repeater_hit": {"name": "Repdigit!", "description": "Count a number made of the same digit (e.g., 111, 2222)", "emoji": "🔁"},
        "palindrome_hit": {"name": "Palindrome!", "description": "Count a palindrome number (reads the same forward/backward)", "emoji": "🪞"},
        "seq_up": {"name": "Going Up", "description": "Count an ascending sequence (e.g., 123, 4567)", "emoji": "⏫"},
        "seq_down": {"name": "Going Down", "description": "Count a descending sequence (e.g., 321, 7654)", "emoji": "⏬"},
        "square_hit": {"name": "Square One", "description": "Count a perfect square (e.g., 49, 144)", "emoji": "◼️"},
        "prime_time": {"name": "Prime Time", "description": "Count a prime number under 2000", "emoji": "🔹"},
        "daily_star": {"name": "Daily Star", "description": "Hit today's target last digit", "emoji": "🌟"},
        # Calculus / Math-themed extras
        "calc_cube": {"name": "Cubic!", "description": "Count a perfect cube (e.g., 27, 64, 125)", "emoji": "🧊"},
        "calc_factorial": {"name": "Factorial!", "description": "Count a factorial number (e.g., 24, 120, 720)", "emoji": "🧮"},
        "calc_triangular": {"name": "Triangular!", "description": "Count a triangular number (e.g., 15, 21, 28)", "emoji": "🔺"},
        "calc_pi": {"name": "Pi Slice", "description": "Hit a π-approx number (ends with 314)", "emoji": "🥧"},
        "calc_e": {"name": "Euler's Touch", "description": "Hit an e-approx number (ends with 2718)", "emoji": "📈"},
        # New numeric curiosities
        "fib_hit": {"name": "Fibonacci!", "description": "Count a Fibonacci number (under 1,000,000)", "emoji": "🌀"},
        "armstrong_hit": {"name": "Narcissistic!", "description": "Count a narcissistic (Armstrong) number", "emoji": "💎"},

        # Variator achievements (difficulty-profile toggles)
        "var_limited_hud_streak_10": {"name": "Blind Counter", "description": "Get a 10-count streak with Limited HUD enabled", "emoji": "🕶️"},
        "var_skip_chance_25": {"name": "Skip Roulette", "description": "Participate in 25 counts while Skip Chance is enabled", "emoji": "🎲"},
        "var_random_range_50": {"name": "Bringushell Veteran", "description": "Participate in 50 counts while Random Range is enabled", "emoji": "🌪️"},
        "var_events_enabled_25": {"name": "Protocol Candidate", "description": "Hit a 25th count while Events are enabled", "emoji": "🧪"},
        "var_regression_rally": {"name": "Regression Rally", "description": "After being the last failure, rebuild a 3-count streak with Regression enabled", "emoji": "🔁"},

        # Psychotic achievements (cosmetic overlays)
        "psy_paranoia_exposure": {"name": "Watched", "description": "Count while Paranoia is active", "emoji": "👁️"},
        "psy_dissociation_exposure": {"name": "Numb", "description": "Count while Dissociation is active", "emoji": "🫥"},
        "psy_dejavu_exposure": {"name": "Looped", "description": "Count while Deja Vu is active", "emoji": "♻️"},
        "psy_under_observation": {"name": "Under Observation", "description": "Reach a 5-count streak while any Psychotic overlay is active", "emoji": "🧠"},
        "psy_trial_complete": {"name": "Trial Complete", "description": "Count under Paranoia, Dissociation, and Deja Vu", "emoji": "📋"},
    }
    
    # --- Pattern helpers ---
    @staticmethod
    def _is_palindrome(n: int) -> bool:
        s = str(n)
        return len(s) >= 3 and s == s[::-1]

    @staticmethod
    def _is_repeater(n: int) -> bool:
        s = str(n)
        return len(s) >= 3 and all(ch == s[0] for ch in s)

    @staticmethod
    def _is_seq_up(n: int) -> bool:
        s = str(n)
        if len(s) < 3:
            return False
        for i in range(len(s) - 1):
            if not (s[i].isdigit() and s[i+1].isdigit() and int(s[i]) + 1 == int(s[i+1])):
                return False
        return True

    @staticmethod
    def _is_seq_down(n: int) -> bool:
        s = str(n)
        if len(s) < 3:
            return False
        for i in range(len(s) - 1):
            if not (s[i].isdigit() and s[i+1].isdigit() and int(s[i]) - 1 == int(s[i+1])):
                return False
        return True

    @staticmethod
    def _is_square(n: int) -> bool:
        if n < 25:
            return False
        r = int(n ** 0.5)
        return r * r == n

    @staticmethod
    def _is_cube(n: int) -> bool:
        if n < 27:
            return False
        r = int(round(n ** (1/3)))
        # guard against rounding errors
        for k in (r-1, r, r+1):
            if k > 0 and k * k * k == n:
                return True
        return False

    @staticmethod
    def _is_factorial(n: int) -> bool:
        # check k! for k>=3 up to a reasonable bound
        f = 1
        k = 1
        while f < n and k <= 12:
            k += 1
            f *= k
        return f == n and k >= 3

    @staticmethod
    def _is_triangular(n: int) -> bool:
        if n < 6:  # 3 and 6 are first interesting ones; keep small noise down but allow 6
            return n in (3, 6)
        x = 8*n + 1
        r = int(x ** 0.5)
        return r*r == x

    @staticmethod
    def _ends_with(n: int, tail: str) -> bool:
        s = str(n)
        return s.endswith(tail)

    @staticmethod
    def _is_prime(n: int) -> bool:
        if n <= 1:
            return False
        if n <= 3:
            return True
        if n % 2 == 0 or n % 3 == 0:
            return n in (2, 3)
        i = 5
        while i * i <= n and i <= 2000:  # soft cap to keep checks light
            if n % i == 0 or n % (i + 2) == 0:
                return False
            i += 6
        return n <= 2000

    @staticmethod
    def _is_fibonacci(n: int) -> bool:
        """Check if n is a Fibonacci number using 5n^2±4 perfect square test.
        Constrain to n <= 1,000,000 to avoid noise/spam achievements at huge scales.
        """
        if n < 0 or n > 1_000_000:
            return False
        def is_perfect_square(x: int) -> bool:
            r = int(x ** 0.5)
            return r*r == x
        return is_perfect_square(5*n*n + 4) or is_perfect_square(5*n*n - 4)

    @staticmethod
    def _is_armstrong(n: int) -> bool:
        """Detect narcissistic (Armstrong) numbers. Require n >= 100 to keep it special."""
        if n < 100:
            return False
        s = str(n)
        p = len(s)
        return sum((ord(c)-48) ** p for c in s) == n

    @staticmethod
    def check_achievements(
        user_id: int,
        guild_data: dict,
        current_stats: dict,
        counted_number: int,
        now: Optional[datetime.datetime] = None,
        elapsed_seconds: Optional[float] = None,
    ) -> List[str]:
        """Evaluate and persist newly unlocked achievements for a user.
        Inputs:
        - user_id: int (discord user id)
        - guild_data: dict (mutable, persisted after changes)
        - current_stats: { total_counts: int, current_streak: int }
        - counted_number: the number the user just posted (pre-increment)
        - now: utc datetime of the count
        - elapsed_seconds: seconds since previous count (for speed achievements)
        Outputs: list of newly earned achievement IDs
        """
        if now is None:
            now = datetime.datetime.utcnow()
        achievements = guild_data.get("achievements", {})
        user_achievements = achievements.get(str(user_id), [])
        # Ensure it's a list
        if not isinstance(user_achievements, list):
            user_achievements = []
        new_achievements: List[str] = []
        
        user_count = int(current_stats.get("total_counts", 0) or 0)
        user_streak = int(current_stats.get("current_streak", 0) or 0)

        # Difficulty profile snapshot (used for variator achievements)
        difficulty_mode = (guild_data.get("difficulty_mode") or "normal").lower().strip()
        profile = DIFFICULTY_PROFILES.get(difficulty_mode) or DIFFICULTY_PROFILES.get("normal") or {}
        limited_hud = bool(profile.get("limited_hud", False))
        skip_chance = float(profile.get("skip_chance", 0.0) or 0.0)
        random_range = int(profile.get("random_range", 0) or 0)
        events_enabled = float(profile.get("event_chance", 0.0) or 0.0) > 0.0
        regression_enabled = bool(profile.get("regression", True))
        
        # Core thresholds
        conditions = [
            ("first_count", user_count >= 1),
            ("streak_5", user_streak >= 5),
            ("streak_10", user_streak >= 10),
            ("streak_25", user_streak >= 25),
            ("streak_50", user_streak >= 50),
            ("streak_100", user_streak >= 100),
            ("count_10", user_count >= 10),
            ("count_100", user_count >= 100),
            ("count_250", user_count >= 250),
            ("count_500", user_count >= 500),
            ("count_1000", user_count >= 1000),
            ("count_2500", user_count >= 2500),
            ("count_5000", user_count >= 5000),
            ("count_10000", user_count >= 10000),
            # Use the counted number to avoid off-by-one from incremented current_number
            ("milestone_100", counted_number >= 100),
            ("milestone_420", counted_number >= 420),
            ("milestone_500", counted_number >= 500),
            ("milestone_1000", counted_number >= 1000),
            ("milestone_1337", counted_number >= 1337),
            ("milestone_5000", counted_number >= 5000),
            ("milestone_10000", counted_number >= 10000),
        ]
        
        # Time-based achievements
        hour = now.hour
        conditions.extend([
            ("night_owl", 2 <= hour < 6),
            ("early_bird", 5 <= hour < 8),
            ("speed_demon", (elapsed_seconds is not None and elapsed_seconds <= 10.0)),
            ("perfect_day", user_streak >= 50),  # interpreted as 50 streak without fail
        ])
        
        # Pattern-based achievements
        if CountingAchievements._is_repeater(counted_number):
            conditions.append(("repeater_hit", True))
        if CountingAchievements._is_palindrome(counted_number):
            conditions.append(("palindrome_hit", True))
        if CountingAchievements._is_seq_up(counted_number):
            conditions.append(("seq_up", True))
        if CountingAchievements._is_seq_down(counted_number):
            conditions.append(("seq_down", True))
        if CountingAchievements._is_square(counted_number):
            conditions.append(("square_hit", True))
        if CountingAchievements._is_prime(counted_number):
            conditions.append(("prime_time", True))
        # Numeric curiosities
        if CountingAchievements._is_fibonacci(counted_number):
            conditions.append(("fib_hit", True))
        if CountingAchievements._is_armstrong(counted_number):
            conditions.append(("armstrong_hit", True))
        # Calculus-themed
        if CountingAchievements._is_cube(counted_number):
            conditions.append(("calc_cube", True))
        if CountingAchievements._is_factorial(counted_number):
            conditions.append(("calc_factorial", True))
        if CountingAchievements._is_triangular(counted_number):
            conditions.append(("calc_triangular", True))
        if CountingAchievements._ends_with(counted_number, "314"):
            conditions.append(("calc_pi", True))
        if CountingAchievements._ends_with(counted_number, "2718"):
            conditions.append(("calc_e", True))
        
        # Recovery-based: if there have been failures in the run and user rebuilt a streak
        total_failures = int(guild_data.get("failures", 0) or 0)
        if total_failures > 0 and user_streak >= 10:
            conditions.append(("fail_recovery", True))

        # Variator-based achievements (tied to difficulty-profile toggles)
        if limited_hud and user_streak >= 10:
            conditions.append(("var_limited_hud_streak_10", True))
        if skip_chance > 0.0 and user_count >= 25:
            conditions.append(("var_skip_chance_25", True))
        if random_range > 0 and user_count >= 50:
            conditions.append(("var_random_range_50", True))
        if events_enabled and (counted_number % 25 == 0):
            conditions.append(("var_events_enabled_25", True))
        # If Regression is enabled and this user was the last person to fail, reward a small comeback streak.
        if regression_enabled:
            try:
                last_fail_user = guild_data.get("last_fail_user", None)
                lives_now = int(guild_data.get("lives", 0) or 0)
            except Exception:
                last_fail_user = None
                lives_now = 0
            if lives_now > 0 and str(last_fail_user) == str(user_id) and user_streak >= 3:
                conditions.append(("var_regression_rally", True))

        # Psychotic-based achievements (cosmetic overlays)
        try:
            psy_raw = guild_data.get("psychotic_active", None)
            psy = str(psy_raw).strip().lower() if psy_raw else ""
        except Exception:
            psy = ""
        if psy == "paranoia":
            conditions.append(("psy_paranoia_exposure", True))
        if psy == "dissociation":
            conditions.append(("psy_dissociation_exposure", True))
        if psy == "dejavu":
            conditions.append(("psy_dejavu_exposure", True))
        if psy and user_streak >= 5:
            conditions.append(("psy_under_observation", True))
        
        for ach_id, cond in conditions:
            if cond and ach_id in CountingAchievements.ACHIEVEMENTS:
                if ach_id not in user_achievements:
                    user_achievements.append(ach_id)
                    new_achievements.append(ach_id)

        # Meta: once the user has experienced all three psychotics, award the triad.
        try:
            if (
                ("psy_paranoia_exposure" in user_achievements)
                and ("psy_dissociation_exposure" in user_achievements)
                and ("psy_dejavu_exposure" in user_achievements)
            ):
                if (
                    ("psy_triad_complete" in CountingAchievements.ACHIEVEMENTS)
                    and ("psy_triad_complete" not in user_achievements)
                ):
                    user_achievements.append("psy_triad_complete")
                    new_achievements.append("psy_triad_complete")
        except Exception:
            pass
        
        # Persist
        achievements[str(user_id)] = user_achievements
        guild_data["achievements"] = achievements
        return new_achievements

class CountingView(discord.ui.View):
    """Interactive view for counting game management"""
    
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
    
    @discord.ui.button(label="📊 Stats", style=discord.ButtonStyle.primary)
    async def show_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog.create_stats_embed(self.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🏆 Achievements", style=discord.ButtonStyle.secondary)
    async def show_achievements(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog.create_achievements_embed(self.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="📈 Leaderboard", style=discord.ButtonStyle.success)
    async def show_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog.create_leaderboard_embed(self.guild_id)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="ℹ️ Info", style=discord.ButtonStyle.secondary)
    async def show_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog.create_info_embed(self.guild_id)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class DifficultyModal(discord.ui.Modal, title="Set Counting Difficulty"):
    def __init__(self, cog, guild_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
    
    difficulty = discord.ui.TextInput(
        label="Difficulty Mode",
        placeholder="normal, hard, nightmare, bringushell, variortus",
        max_length=20,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        difficulty = self.difficulty.value.lower().strip()
        valid_modes = ["normal", "hard", "nightmare", "bringushell", "variortus"]
        
        if difficulty not in valid_modes:
            await interaction.response.send_message(
                f"❌ Invalid difficulty! Choose from: {', '.join(valid_modes)}", 
                ephemeral=True
            )
            return
        
        guild_data = self.cog.data_manager.load_guild_data(self.guild_id)
        guild_data["difficulty_mode"] = difficulty
        self.cog.data_manager.save_guild_data(self.guild_id, guild_data)
        
        descriptions = {
            "normal": "Standard counting rules",
            "hard": "Faster timeout, more strict rules",
            "nightmare": "Very fast timeout, no mistakes allowed",
            "bringushell": "Randomized expected numbers",
            "variortus": "Standard rules (opt-in theme gate)"
        }
        
        await interaction.response.send_message(
            f"✅ Difficulty set to **{difficulty.title()}**\n{descriptions[difficulty]}"
        )

class NumberCheckModal(discord.ui.Modal, title="Check Your Number"):
    def __init__(self, cog: "BringusCounting", guild_id: int, expected: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.expected_value = expected
        self.number_input = discord.ui.TextInput(
            label="Enter the number you'll send",
            placeholder=str(expected),
            required=True,
            max_length=10
        )
        self.add_item(self.number_input)

    async def on_submit(self, interaction: discord.Interaction):
        content = (self.number_input.value or "").strip()
        ok = content.isdigit() and int(content) == int(self.expected_value)
        if ok:
            await interaction.response.send_message(
                f"✅ Looks good! Next number is `{self.expected_value}`.\nTip: Long-press to copy then paste it in the counting channel.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ That doesn't match. Expected `{self.expected_value}`.",
                ephemeral=True
            )

class MobileHelperView(discord.ui.View):
    def __init__(self, cog: "BringusCounting", guild_id: int, expected: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.expected = expected

    @discord.ui.button(label="Show Next Number", style=discord.ButtonStyle.primary)
    async def show_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"Next number: `{self.expected}`\nLong-press to copy on mobile.",
            ephemeral=True
        )

    @discord.ui.button(label="Check My Number", style=discord.ButtonStyle.secondary)
    async def check_number(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = NumberCheckModal(self.cog, self.guild_id, self.expected)
        await interaction.response.send_modal(modal)

class BringusCounting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_manager = CountingData()
        # Reaction rate limiting helpers (per-channel)
        self._reaction_locks: Dict[int, Lock] = {}
        self._last_reaction_at: Dict[int, float] = {}
        # Simple dedupe store for processed message IDs (to avoid double-processing)
        self._processed_messages: Dict[int, None] = {}
        # Additional guards against duplicate announcements (per short window)
        self._recent_announcements: Dict[str, float] = {}
        # Last snapshot for undo (per guild id)
        self._last_snapshot: Dict[int, Optional[dict]] = {}

        # Numeric spam reinforcement (in-memory, per-process)
        # user_id -> last accepted numeric attempt (monotonic)
        self._numeric_user_last_at: Dict[int, float] = {}
        # channel_id -> last accepted numeric attempt (monotonic)
        self._numeric_channel_last_at: Dict[int, float] = {}
        # user_id -> (window_start_monotonic, count)
        self._numeric_user_burst: Dict[int, Tuple[float, int]] = {}
        # user_id -> ignore-until (monotonic)
        self._numeric_user_mute_until: Dict[int, float] = {}

        # Cosmetic: recent bot output cache for psychotics like 'dejavu'
        # channel_id -> list[(monotonic_ts, kind, text)]
        self._recent_bot_lines: Dict[int, List[Tuple[float, str, str]]] = {}
        # channel_id -> last time we emitted a dejavu line
        self._dejavu_last_sent_at: Dict[int, float] = {}
        try:
            self.ANNOUNCE_DEDUP_WINDOW = float(os.getenv("ANNOUNCE_DEDUP_WINDOW", "5.0"))
        except Exception:
            self.ANNOUNCE_DEDUP_WINDOW = 5.0
        # Minimum time between reactions in same channel (seconds); tweak via env
        try:
            self.REACTION_MIN_INTERVAL = float(os.getenv("REACTION_MIN_INTERVAL", "0.40"))
        except Exception:
            self.REACTION_MIN_INTERVAL = 0.40

        # Confusion guide (Easterman briefings/posters): explain why a count failed.
        # Env toggles are optional; defaults are enabled + low spam.
        try:
            raw = (os.getenv("COUNTING_CONFUSION_GUIDE", "1") or "1").strip().lower()
            self.COUNTING_CONFUSION_GUIDE = raw not in ("0", "false", "no", "off")
        except Exception:
            self.COUNTING_CONFUSION_GUIDE = True
        try:
            self.COUNTING_CONFUSION_GUIDE_COOLDOWN = float(os.getenv("COUNTING_CONFUSION_GUIDE_COOLDOWN", "20.0"))
        except Exception:
            self.COUNTING_CONFUSION_GUIDE_COOLDOWN = 20.0

        # Numeric spam prevention defaults (tweakable via env)
        try:
            self.COUNTING_MAX_DIGITS = int(os.getenv("COUNTING_MAX_DIGITS", "12"))
        except Exception:
            self.COUNTING_MAX_DIGITS = 12

        try:
            self.COUNTING_NUMERIC_USER_COOLDOWN = float(os.getenv("COUNTING_NUMERIC_USER_COOLDOWN", "1.0"))
        except Exception:
            self.COUNTING_NUMERIC_USER_COOLDOWN = 1.0

        try:
            self.COUNTING_NUMERIC_CHANNEL_COOLDOWN = float(os.getenv("COUNTING_NUMERIC_CHANNEL_COOLDOWN", "0.35"))
        except Exception:
            self.COUNTING_NUMERIC_CHANNEL_COOLDOWN = 0.35

        try:
            self.COUNTING_NUMERIC_SPAM_WINDOW = float(os.getenv("COUNTING_NUMERIC_SPAM_WINDOW", "5.0"))
        except Exception:
            self.COUNTING_NUMERIC_SPAM_WINDOW = 5.0

        try:
            self.COUNTING_NUMERIC_SPAM_STRIKES = int(os.getenv("COUNTING_NUMERIC_SPAM_STRIKES", "6"))
        except Exception:
            self.COUNTING_NUMERIC_SPAM_STRIKES = 6

        try:
            self.COUNTING_NUMERIC_SPAM_MUTE = float(os.getenv("COUNTING_NUMERIC_SPAM_MUTE", "10.0"))
        except Exception:
            self.COUNTING_NUMERIC_SPAM_MUTE = 10.0
        
        
        # Load guild configurations
        self.guild_configs = {}
        self.load_all_guild_configs()
        self.special_numbers = load_special_numbers(self.data_manager.data_dir)

    async def cog_load(self):
        """Initialize background tasks when cog is loaded"""
        self.save_data_task.start()
        self.daily_reset_task.start()

    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        if hasattr(self, 'save_data_task') and self.save_data_task.is_running():
            self.save_data_task.cancel()
        if hasattr(self, 'daily_reset_task') and self.daily_reset_task.is_running():
            self.daily_reset_task.cancel()
        self.save_all_guild_configs()

    def load_all_guild_configs(self):
        """Load configurations for all guilds"""
        # Keep legacy fields (including webhook_url) but do not use them
        try:
            config_file = os.path.join(self.data_manager.data_dir, "guild_configs.json")
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    self.guild_configs = json.load(f)
        except Exception as e:
            logging.error(f"Failed to load guild configs: {e}")
            self.guild_configs = {}

    def save_all_guild_configs(self):
        """Save configurations for all guilds"""
        try:
            config_file = os.path.join(self.data_manager.data_dir, "guild_configs.json")
            with open(config_file, 'w') as f:
                json.dump(self.guild_configs, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save guild configs: {e}")

    # --- Admin helpers: snapshot and restore ---
    def _snapshot_guild(self, guild_id: int):
        try:
            data = self.data_manager.load_guild_data(guild_id)
            # Deep copy via JSON round-trip to avoid shared refs
            self._last_snapshot[guild_id] = json.loads(json.dumps(data))
        except Exception:
            self._last_snapshot[guild_id] = None

    def _restore_snapshot(self, guild_id: int) -> bool:
        snap = self._last_snapshot.get(guild_id)
        if not snap:
            return False
        try:
            self.data_manager.save_guild_data(guild_id, snap)
            return True
        except Exception:
            return False

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Initialize data when bot joins a new guild"""
        if str(guild.id) not in self.guild_configs:
            self.guild_configs[str(guild.id)] = {
                "counting_channel": None,
                "webhook_url": None,  # legacy, unused
                "is_personal_guild": False
            }

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        # Avoid double-processing the same Discord message (rare duplicate events)
        if message.id in self._processed_messages:
            return
        # Do not mark as processed here; let process_count handle it atomically
        
        guild_id = message.guild.id
        guild_data = self.data_manager.load_guild_data(guild_id)
        
        # Check if this is the counting channel
        if guild_data.get("channel_id") != message.channel.id:
            return

        content = message.content.strip()
        if not content.isdigit():
            return

        # --- Numeric spam reinforcement ---
        # 1) Guard against absurdly large ints (conversion + downstream ops).
        # Allow some headroom above the current expected number's digit length.
        try:
            current_expected = int(guild_data.get("current_number", 1) or 1)
        except Exception:
            current_expected = 1
        dynamic_cap = max(int(self.COUNTING_MAX_DIGITS or 12), len(str(current_expected)) + 3)
        if len(content) > dynamic_cap:
            return

        # 2) Rate-limit numeric attempts so floods don't drain lives or overwhelm processing.
        now_m = float(time.monotonic())
        user_id = int(message.author.id)
        channel_id = int(message.channel.id)

        mute_until = float(self._numeric_user_mute_until.get(user_id, 0.0) or 0.0)
        if mute_until and now_m < mute_until:
            return

        user_last = float(self._numeric_user_last_at.get(user_id, 0.0) or 0.0)
        if self.COUNTING_NUMERIC_USER_COOLDOWN and (now_m - user_last) < float(self.COUNTING_NUMERIC_USER_COOLDOWN):
            window_start, count = self._numeric_user_burst.get(user_id, (now_m, 0))
            if (now_m - float(window_start)) > float(self.COUNTING_NUMERIC_SPAM_WINDOW or 5.0):
                window_start, count = now_m, 0
            count += 1
            self._numeric_user_burst[user_id] = (float(window_start), int(count))
            if int(count) >= int(self.COUNTING_NUMERIC_SPAM_STRIKES or 6):
                self._numeric_user_mute_until[user_id] = now_m + float(self.COUNTING_NUMERIC_SPAM_MUTE or 10.0)
                self._numeric_user_burst[user_id] = (now_m, 0)
            return

        chan_last = float(self._numeric_channel_last_at.get(channel_id, 0.0) or 0.0)
        if self.COUNTING_NUMERIC_CHANNEL_COOLDOWN and (now_m - chan_last) < float(self.COUNTING_NUMERIC_CHANNEL_COOLDOWN):
            return

        # Accept this attempt
        self._numeric_user_last_at[user_id] = now_m
        self._numeric_channel_last_at[channel_id] = now_m
        if user_id in self._numeric_user_burst:
            self._numeric_user_burst[user_id] = (now_m, 0)

        number = int(content)
        await self.process_count(message, number, guild_data)

    async def process_count(self, message, number: int, guild_data: dict):
        """Process a counting attempt"""
        guild_id = message.guild.id
        user_id = message.author.id
        blackout_active = self._is_blackout_active(guild_data)
        # Secondary guard in case on_message dedupe missed
        if message.id in self._processed_messages:
            return
        self._processed_messages[message.id] = None
        # Keep dedupe map from growing unbounded
        if len(self._processed_messages) > 5000:
            try:
                self._processed_messages.pop(next(iter(self._processed_messages)))
            except Exception:
                self._processed_messages.clear()

        # RLGL expiry announcement: ensure it ends cleanly and doesn't stay stuck.
        try:
            ended = await self._end_rlgl_if_expired(message.channel, message.channel.id, guild_data)
            if ended:
                self.data_manager.save_guild_data(guild_id, guild_data)
        except Exception:
            pass

        # Psychotic lifecycle announcements (start/end).
        try:
            ended_psy = await self._end_psychotic_if_expired(message.channel, message.channel.id, guild_data)
            started_psy = await self._maybe_announce_psychotic_start(message.channel, message.channel.id, guild_data)
            if ended_psy or started_psy:
                self.data_manager.save_guild_data(guild_id, guild_data)
        except Exception:
            pass

        # Countdown enforcement (only affects numeric count attempts while active).
        countdown_active = bool(guild_data.get("countdown_active", False))
        countdown_user_id_raw = guild_data.get("countdown_user_id", None)
        countdown_expires_raw = guild_data.get("countdown_expires_at", None)
        if countdown_active:
            try:
                countdown_user_id = int(countdown_user_id_raw) if countdown_user_id_raw is not None else None
            except Exception:
                countdown_user_id = None
            try:
                countdown_expires_at = float(countdown_expires_raw) if countdown_expires_raw is not None else None
            except Exception:
                countdown_expires_at = None

            # If state is malformed, end the countdown safely and proceed normally.
            if countdown_user_id is None:
                guild_data["countdown_active"] = False
                guild_data["countdown_user_id"] = None
                guild_data["countdown_expires_at"] = None
                self.data_manager.save_guild_data(guild_id, guild_data)
                countdown_active = False
            else:
                now_ts = float(time.time())
                if countdown_expires_at is not None and now_ts > countdown_expires_at:
                    # Expired before success: end countdown + apply existing safe failure logic.
                    guild_data["countdown_active"] = False
                    guild_data["countdown_user_id"] = None
                    guild_data["countdown_expires_at"] = None

                    guild_data["lives"] = int(guild_data.get("lives", 3) or 3) - 1
                    guild_data["failures"] = int(guild_data.get("failures", 0) or 0) + 1
                    guild_data["last_fail_user"] = str(countdown_user_id)
                    try:
                        streaks = guild_data.get("streaks", {})
                        streaks[str(countdown_user_id)] = 0
                        guild_data["streaks"] = streaks
                    except Exception:
                        pass

                    # Regression: step the expected number backward (only if not game over).
                    if int(guild_data.get("lives", 0) or 0) > 0:
                        try:
                            self.apply_regression(guild_data)
                        except Exception:
                            pass

                    line = get_murkoff_line(MURKOFF_MESSAGES.get("event_end", []))
                    if line:
                        await message.channel.send(line)

                    if guild_data.get("lives", 0) <= 0:
                        await self.handle_game_over(message, guild_data)

                    self.data_manager.save_guild_data(guild_id, guild_data)
                    return

                # Only the primed user may post the next number during countdown.
                if user_id != countdown_user_id:
                    try:
                        if blackout_active:
                            # Intentional silence is part of Blackout, but countdown enforcement
                            # should still feel deliberate (not broken). Emit a minimal system line
                            # on a short per-user cooldown.
                            key = f"blk:countdown_block:{guild_id}:{message.channel.id}:{user_id}"
                            now_ts = time.monotonic()
                            last = self._recent_announcements.get(key)
                            if last is None or (now_ts - last) > 3.0:
                                await self._send_and_remember(
                                    message.channel,
                                    message.channel.id,
                                    "COUNTDOWN ACTIVE. WAIT FOR AUTHORIZATION.",
                                    "murkoff",
                                )
                                self._recent_announcements[key] = now_ts
                        elif not self.is_limited_hud(guild_data):
                            await self.safe_add_reaction(message, "💣")
                    except Exception:
                        pass
                    return
        
        # Check if same user counted twice (No Consecutive).
        # Countdown exception: during Countdown, allow the primed user to count again.
        if self.is_no_consecutive(guild_data):
            if guild_data.get("last_user_id") == user_id and not (countdown_active and user_id == int(countdown_user_id_raw or 0)):
                if not blackout_active:
                    await self.safe_add_reaction(message, "💀")
                    await message.channel.send(
                        f"❌ <@{user_id}> You cannot count twice in a row! Lives: {guild_data.get('lives', 3)}"
                    )
                else:
                    await message.channel.send(
                        f"<@{user_id}> You cannot count twice in a row. Lives: {guild_data.get('lives', 3)}"
                    )

                # Confusion guide: explain the rule that caused the failure.
                try:
                    await self._maybe_send_confusion_guide(
                        message,
                        reason="no_consecutive",
                        expected=None,
                        got=number,
                        before_current=None,
                        after_current=None,
                    )
                except Exception:
                    pass
                return

        # Determine expected number based on difficulty
        expected_number = self.get_expected_number(guild_data, user_id=user_id)
        
        if number != expected_number:
            await self.handle_wrong_count(message, guild_data, expected_number, got=number)
            return

        # Countdown success: primed user posted correct number before expiry.
        if countdown_active:
            expires_at = None
            expires_raw = guild_data.get("countdown_expires_at", None)
            if expires_raw is not None:
                try:
                    expires_at = float(expires_raw)
                except Exception:
                    expires_at = None
            if expires_at is None or float(time.time()) <= expires_at:
                guild_data["countdown_active"] = False
                guild_data["countdown_user_id"] = None
                guild_data["countdown_expires_at"] = None
                line = get_murkoff_line(MURKOFF_MESSAGES.get("event_end", []))
                if line:
                    await message.channel.send(line)

        # Correct count!
        await self.handle_correct_count(message, number, guild_data)

    def get_expected_number(self, guild_data: dict, user_id: Optional[int] = None) -> int:
        """Get the expected number based on difficulty mode and scope.
        - If difficulty_scope == 'per-user', we do NOT alter the expected number to keep the game shared.
        - If 'global', we apply the selected mode as before.
        """
        current = guild_data.get("current_number", 1)
        scope = guild_data.get("difficulty_scope", "global")
        difficulty = guild_data.get("difficulty_mode", "normal")
        if scope == "per-user":
            # Keep expected strictly sequential to avoid conflicting per-user paths
            return current

        # Passive usage for future escalation-based tuning (no behavior change today)
        try:
            _effective_phase = self.get_effective_phase(guild_data)
        except Exception:
            _effective_phase = 0

        profile = DIFFICULTY_PROFILES.get(difficulty) or DIFFICULTY_PROFILES.get("normal") or {}
        
        if difficulty == "bringushell":
            rr = int(profile.get("random_range", 2) or 2)
            return random.randint(max(1, current - rr), current + rr)
        elif difficulty == "nightmare":
            # In nightmare mode, sometimes the number skips
            skip_chance = float(profile.get("skip_chance", 0.1) or 0.1)
            if random.random() < skip_chance:  # 10% chance to skip
                rr = int(profile.get("random_range", 3) or 3)
                return current + random.randint(1, rr)
        
        return current

    def is_limited_hud(self, guild_data: dict) -> bool:
        """Limited HUD: suppress helpful confirmations (reactions/pattern callouts).

        No new state machine; the toggle lives in the difficulty profile.
        """
        try:
            difficulty = (guild_data.get("difficulty_mode") or "normal").lower()
            profile = DIFFICULTY_PROFILES.get(difficulty) or DIFFICULTY_PROFILES.get("normal") or {}
            return bool(profile.get("limited_hud", False))
        except Exception:
            return False

    def is_no_consecutive(self, guild_data: dict) -> bool:
        """No Consecutive: disallow the same user counting twice in a row."""
        try:
            difficulty = (guild_data.get("difficulty_mode") or "normal").lower()
            profile = DIFFICULTY_PROFILES.get(difficulty) or DIFFICULTY_PROFILES.get("normal") or {}
            return bool(profile.get("no_consecutive", True))
        except Exception:
            return True

    def is_silent_fail(self, guild_data: dict) -> bool:
        """Silent Fail: wrong-number feedback does not reveal the expected value."""
        try:
            difficulty = (guild_data.get("difficulty_mode") or "normal").lower()
            profile = DIFFICULTY_PROFILES.get(difficulty) or DIFFICULTY_PROFILES.get("normal") or {}
            return bool(profile.get("silent_fail", False))
        except Exception:
            return False

    def is_regression(self, guild_data: dict) -> bool:
        """Regression: failures push the expected number backward."""
        try:
            difficulty = (guild_data.get("difficulty_mode") or "normal").lower()
            profile = DIFFICULTY_PROFILES.get(difficulty) or DIFFICULTY_PROFILES.get("normal") or {}
            return bool(profile.get("regression", False))
        except Exception:
            return False

    def get_regression_step(self, guild_data: dict) -> int:
        try:
            difficulty = (guild_data.get("difficulty_mode") or "normal").lower()
            profile = DIFFICULTY_PROFILES.get(difficulty) or DIFFICULTY_PROFILES.get("normal") or {}
            step = int(profile.get("regression_step", 1) or 1)
            return max(1, step)
        except Exception:
            return 1

    def apply_regression(self, guild_data: dict):
        if not self.is_regression(guild_data):
            return
        current = int(guild_data.get("current_number", 1) or 1)
        step = self.get_regression_step(guild_data)
        guild_data["current_number"] = max(1, current - step)

    def _get_psychotic_active(self, guild_data: dict) -> Optional[str]:
        """Cosmetic-only psychotic state with optional expiration.

        Returns the active psychotic string (e.g. 'paranoia') or None.
        If an expiration is set and has passed, returns None.

        Note: this accessor does NOT mutate `guild_data`. Expiration clearing +
        announcements are handled by `_end_psychotic_if_expired`.
        """
        active = guild_data.get("psychotic_active", None)
        if not active:
            return None

        expires_at = guild_data.get("psychotic_expires_at", None)
        if expires_at is None:
            return str(active)

        try:
            if float(time.time()) > float(expires_at):
                return None
        except Exception:
            # If malformed, treat as non-expiring to avoid deleting state unexpectedly.
            return str(active)

        return str(active)

    def _remember_bot_line(self, channel_id: int, text: str, kind: str):
        try:
            if not channel_id or not text:
                return
            text = str(text).strip()
            if not text:
                return
            now_ts = time.monotonic()
            buf = self._recent_bot_lines.get(channel_id)
            if buf is None:
                buf = []
                self._recent_bot_lines[channel_id] = buf
            buf.append((now_ts, str(kind), text))
            if len(buf) > 30:
                del buf[: len(buf) - 30]
        except Exception:
            return

    async def _send_and_remember(self, channel: discord.abc.Messageable, channel_id: int, text: str, kind: str) -> bool:
        """Send a message and remember it for cosmetic effects.

        Returns True if a send was attempted successfully.
        """
        try:
            await channel.send(text)
            self._remember_bot_line(channel_id, text, kind)
            return True
        except Exception:
            return False

    def _resolve_guild_channel_for_announcements(
        self,
        guild: "discord.Guild",
        guild_data: dict,
    ) -> Optional[discord.abc.Messageable]:
        """Pick a channel for Murkoff announcements.

        Priority:
        1) Persisted `channel_id` in guild_data
        2) Legacy `guild_configs[guild_id]['counting_channel']`
        """
        channel_id = guild_data.get("channel_id")
        if channel_id:
            try:
                ch = guild.get_channel(int(channel_id))
                if ch is not None and hasattr(ch, "send"):
                    return ch  # type: ignore[return-value]
            except Exception:
                pass

        try:
            cfg = self.guild_configs.get(str(guild.id), {})
            cfg_ch_id = cfg.get("counting_channel")
            if cfg_ch_id:
                ch = guild.get_channel(int(cfg_ch_id))
                if ch is not None and hasattr(ch, "send"):
                    return ch  # type: ignore[return-value]
        except Exception:
            pass

        return None

    async def _cleanup_murkoff_state_for_guild(self, guild: "discord.Guild") -> None:
        """Periodic safety cleanup for cosmetic states.

        Ensures time-based states don't stay stuck forever if no one counts.
        """
        guild_id = int(guild.id)
        guild_data = self.data_manager.load_guild_data(guild_id)
        changed = False

        try:
            now_ts = float(time.time())
        except Exception:
            now_ts = 0.0

        channel = self._resolve_guild_channel_for_announcements(guild, guild_data)
        channel_id = getattr(channel, "id", None)

        # 1) Countdown expiration
        try:
            if bool(guild_data.get("countdown_active", False)):
                expires_raw = guild_data.get("countdown_expires_at", None)
                expires_at = float(expires_raw) if expires_raw is not None else None
                if expires_at is not None and now_ts > expires_at:
                    guild_data["countdown_active"] = False
                    guild_data["countdown_user_id"] = None
                    guild_data["countdown_expires_at"] = None
                    changed = True

                    # Announce only if we can resolve a channel.
                    if channel and channel_id:
                        codename = MURKOFF_CODENAMES.get("countdown", "COUNTDOWN")
                        line = get_murkoff_line(MURKOFF_MESSAGES.get("event_end", [])) or "PROTOCOL CONCLUDED."
                        await self._send_and_remember(channel, int(channel_id), f"**{codename}**\n{line}", "murkoff")
        except Exception:
            pass

        # 2) RLGL expiration
        try:
            if bool(guild_data.get("rlgl_active", False)):
                expires_raw = guild_data.get("rlgl_expires_at", None)
                expires_at = float(expires_raw) if expires_raw is not None else None
                if expires_at is None or now_ts > expires_at:
                    guild_data["rlgl_active"] = False
                    guild_data["rlgl_state"] = None
                    guild_data["rlgl_expires_at"] = None
                    changed = True

                    if channel and channel_id:
                        codename = MURKOFF_CODENAMES.get("red_light", "RED LIGHT")
                        line = get_murkoff_line(MURKOFF_MESSAGES.get("event_end", [])) or "PROTOCOL CONCLUDED."
                        await self._send_and_remember(channel, int(channel_id), f"**{codename}**\n{line}", "murkoff")
        except Exception:
            pass

        # 3) Psychotic expiration
        try:
            active_raw = guild_data.get("psychotic_active", None)
            expires_raw = guild_data.get("psychotic_expires_at", None)
            if active_raw and expires_raw is not None:
                expires_at = float(expires_raw)
                if now_ts > expires_at:
                    active = str(active_raw).strip().lower()
                    guild_data["psychotic_active"] = None
                    guild_data["psychotic_expires_at"] = None
                    guild_data["psychotic_announced_active"] = None
                    changed = True

                    if channel and channel_id:
                        codename = MURKOFF_CODENAMES.get(active, (active or "PSYCHOTIC").upper())
                        line = get_murkoff_line(MURKOFF_MESSAGES.get("event_end", [])) or "PROTOCOL CONCLUDED."
                        await self._send_and_remember(channel, int(channel_id), f"**{codename}**\n{line}", "murkoff")
        except Exception:
            pass

        # 4) Theme safety: don't keep a theme active if not in variortus anymore.
        try:
            active_theme = self._get_active_theme(guild_data)
            if active_theme in ("permafrost", "blackout"):
                difficulty = str(guild_data.get("difficulty_mode") or "normal").strip().lower()
                if difficulty != "variortus":
                    guild_data["active_theme"] = None
                    guild_data["theme_started_at"] = None
                    changed = True

                    if channel and channel_id:
                        codename = MURKOFF_CODENAMES.get(active_theme, active_theme.upper())
                        line = get_murkoff_line(MURKOFF_MESSAGES.get("event_end", [])) or "PROTOCOL CONCLUDED."
                        await self._send_and_remember(channel, int(channel_id), f"**{codename}**\n{line}", "murkoff")
        except Exception:
            pass

        if changed:
            self.data_manager.save_guild_data(guild_id, guild_data)

    async def _maybe_announce_psychotic_start(
        self,
        channel: discord.abc.Messageable,
        channel_id: int,
        guild_data: dict,
    ) -> bool:
        """Announce psychotic activation once per activation.

        Returns True if we emitted a start announcement.
        """
        active_raw = guild_data.get("psychotic_active", None)
        if not active_raw:
            # Clear any stale announcement marker.
            guild_data["psychotic_announced_active"] = None
            return False

        try:
            active = str(active_raw).strip().lower()
        except Exception:
            active = ""

        if not active:
            guild_data["psychotic_announced_active"] = None
            return False

        announced_raw = guild_data.get("psychotic_announced_active", None)
        try:
            announced = str(announced_raw).strip().lower() if announced_raw else ""
        except Exception:
            announced = ""

        if announced == active:
            return False

        guild_data["psychotic_announced_active"] = active

        codename = MURKOFF_CODENAMES.get(active, active.upper())
        line = get_murkoff_line(MURKOFF_MESSAGES.get("event_start", [])) or "PROTOCOL INITIATED."
        await self._send_and_remember(
            channel,
            channel_id,
            f"**{codename}**\n{line}",
            "murkoff",
        )
        return True

    async def _end_psychotic_if_expired(
        self,
        channel: discord.abc.Messageable,
        channel_id: int,
        guild_data: dict,
    ) -> bool:
        """End psychotic overlay if it has expired.

        Clears state and emits a single Murkoff end message.
        Returns True if we ended an active psychotic.
        """
        active_raw = guild_data.get("psychotic_active", None)
        if not active_raw:
            guild_data["psychotic_announced_active"] = None
            return False

        expires_raw = guild_data.get("psychotic_expires_at", None)
        if expires_raw is None:
            return False

        try:
            expires_at = float(expires_raw)
        except Exception:
            # Malformed expiration: treat as non-expiring (preserve previous behavior).
            return False

        try:
            now_ts = float(time.time())
        except Exception:
            now_ts = 0.0

        if now_ts < expires_at:
            return False

        try:
            active = str(active_raw).strip().lower()
        except Exception:
            active = ""

        guild_data["psychotic_active"] = None
        guild_data["psychotic_expires_at"] = None
        guild_data["psychotic_announced_active"] = None

        codename = MURKOFF_CODENAMES.get(active, (active or "PSYCHOTIC").upper())
        line = get_murkoff_line(MURKOFF_MESSAGES.get("event_end", [])) or "PROTOCOL CONCLUDED."
        await self._send_and_remember(
            channel,
            channel_id,
            f"**{codename}**\n{line}",
            "murkoff",
        )
        return True

    def _is_dissociation_active(self, guild_data: dict) -> bool:
        return self._get_psychotic_active(guild_data) == "dissociation"

    async def _maybe_dissociation_delay(self, guild_data: dict):
        """Cosmetic-only response delay.

        When Dissociation is active, occasionally delay bot feedback by 1–2 seconds.
        """
        if not self._is_dissociation_active(guild_data):
            return
        try:
            if random.random() < 0.20:
                await asyncio.sleep(random.uniform(1.0, 2.0))
        except Exception:
            return

    async def _maybe_send_dissociation_line(self, message: discord.Message, guild_data: dict):
        if not self._is_dissociation_active(guild_data):
            return
        try:
            if random.random() < 0.06:
                await self._maybe_dissociation_delay(guild_data)
                line = random.choice(MURKOFF_DISSOCIATION_LINES)
                if line:
                    await self._send_and_remember(message.channel, message.channel.id, line, "murkoff")
        except Exception:
            return

    async def _maybe_send_paranoia_line(self, message: discord.Message, guild_data: dict):
        if self._get_psychotic_active(guild_data) != "paranoia":
            return
        # Low chance after correct counts.
        try:
            if random.random() < 0.03:
                line = random.choice(MURKOFF_PARANOIA_LINES)
                if line:
                    await self._send_and_remember(message.channel, message.channel.id, line, "murkoff")
        except Exception:
            return

    async def _maybe_send_dejavu_line(self, message: discord.Message, guild_data: dict):
        if self._get_psychotic_active(guild_data) != "dejavu":
            return

        channel_id = getattr(message.channel, "id", None)
        if not channel_id:
            return

        # Subtle repetition, not spam: low chance + per-channel cooldown.
        try:
            now_ts = time.monotonic()
            last = self._dejavu_last_sent_at.get(int(channel_id), 0.0)
            if (now_ts - float(last)) < 25.0:
                return
            if random.random() >= 0.04:
                return

            history = self._recent_bot_lines.get(int(channel_id)) or []
            if len(history) < 3:
                return

            # Avoid repeating the immediately previous bot line.
            candidates_murkoff = [t for (ts, kind, t) in history[:-1] if kind == "murkoff"]
            candidates_announce = [t for (ts, kind, t) in history[:-1] if kind != "murkoff"]

            pick_from_murkoff = bool(candidates_murkoff) and (random.random() < 0.50 or not candidates_announce)
            pool = candidates_murkoff if pick_from_murkoff else candidates_announce
            if not pool:
                pool = [t for (_ts, _kind, t) in history[:-1]]
            if not pool:
                return

            line = random.choice(pool)
            if not line:
                return

            self._dejavu_last_sent_at[int(channel_id)] = now_ts
            await message.channel.send(line)
            self._remember_bot_line(int(channel_id), line, "dejavu")
        except Exception:
            return

    # --- Passive difficulty helpers (not wired into logic yet) ---
    def get_escalation_phase(self, count: int) -> int:
        if count < 25:
            return 0
        if count < 50:
            return 1
        if count < 75:
            return 2
        if count < 100:
            return 3
        return 4

    def get_effective_phase(self, guild_data: dict) -> int:
        current_number = int(guild_data.get("current_number", 1) or 1)
        difficulty = (guild_data.get("difficulty_mode") or "normal").lower()
        phase = self.get_escalation_phase(current_number)

        profile = DIFFICULTY_PROFILES.get(difficulty) or DIFFICULTY_PROFILES.get("normal") or {}
        max_phase = int(profile.get("max_phase", 4) or 4)
        return min(phase, max_phase)

    # --- Passive theme helpers (cosmetic-only) ---
    def _get_active_theme(self, guild_data: dict) -> Optional[str]:
        theme = guild_data.get("active_theme", None)
        if not theme:
            return None
        try:
            theme_str = str(theme).strip().lower()
        except Exception:
            return None
        return theme_str or None

    def _is_blackout_active(self, guild_data: dict) -> bool:
        return self._get_active_theme(guild_data) == "blackout"

    def _is_permafrost_active(self, guild_data: dict) -> bool:
        return self._get_active_theme(guild_data) == "permafrost"

    async def _maybe_permafrost_delay(self, guild_data: dict):
        """Cosmetic-only response delay.

        When Permafrost is active, delay non-critical bot outputs by 1–2 seconds.
        """
        if not self._is_permafrost_active(guild_data):
            return
        try:
            await asyncio.sleep(random.uniform(1.0, 2.0))
        except Exception:
            return

    async def _end_permafrost_if_active(
        self,
        channel: discord.abc.Messageable,
        channel_id: int,
        guild_data: dict,
    ) -> bool:
        """End Permafrost theme if active (cosmetic-only).

        Clears `active_theme` and `theme_started_at` and emits a single Murkoff end message.
        Returns True if Permafrost was active and is now ended.
        """
        if self._get_active_theme(guild_data) != "permafrost":
            return False

        guild_data["active_theme"] = None
        guild_data["theme_started_at"] = None

        codename = MURKOFF_CODENAMES.get("permafrost", "PERMAFROST")
        line = get_murkoff_line(MURKOFF_MESSAGES.get("event_end", [])) or "PROTOCOL CONCLUDED."
        await self._send_and_remember(
            channel,
            channel_id,
            f"**{codename}**\n{line}",
            "murkoff",
        )
        return True

    async def _end_blackout_if_active(
        self,
        channel: discord.abc.Messageable,
        channel_id: int,
        guild_data: dict,
    ) -> bool:
        """End Blackout theme if active (cosmetic-only).

        Clears `active_theme` and `theme_started_at` and emits a single Murkoff end message.
        Returns True if Blackout was active and is now ended.
        """
        if self._get_active_theme(guild_data) != "blackout":
            return False

        guild_data["active_theme"] = None
        guild_data["theme_started_at"] = None

        codename = MURKOFF_CODENAMES.get("blackout", "BLACKOUT")
        line = get_murkoff_line(MURKOFF_MESSAGES.get("event_end", [])) or "PROTOCOL CONCLUDED."
        await self._send_and_remember(
            channel,
            channel_id,
            f"**{codename}**\n{line}",
            "murkoff",
        )
        return True

    async def _end_rlgl_if_expired(
        self,
        channel: discord.abc.Messageable,
        channel_id: int,
        guild_data: dict,
    ) -> bool:
        """End RLGL event if expired.

        Clears RLGL state and emits a single Murkoff end message.
        Returns True if RLGL was active and is now ended.
        """
        if not bool(guild_data.get("rlgl_active", False)):
            return False

        expires_raw = guild_data.get("rlgl_expires_at", None)
        expires_at: Optional[float]
        try:
            expires_at = float(expires_raw) if expires_raw is not None else None
        except Exception:
            expires_at = None

        # If malformed or missing, end it to avoid stuck state.
        try:
            now_ts = float(time.time())
        except Exception:
            now_ts = 0.0

        if expires_at is not None and now_ts < expires_at:
            return False

        guild_data["rlgl_active"] = False
        guild_data["rlgl_state"] = None
        guild_data["rlgl_expires_at"] = None

        codename = MURKOFF_CODENAMES.get("red_light", "RED LIGHT")
        line = get_murkoff_line(MURKOFF_MESSAGES.get("event_end", [])) or "PROTOCOL CONCLUDED."
        await self._send_and_remember(
            channel,
            channel_id,
            f"**{codename}**\n{line}",
            "murkoff",
        )
        return True

    async def handle_wrong_count(self, message, guild_data: dict, expected: int, got: Optional[int] = None):
        """Handle incorrect counting attempt"""
        guild_id = message.guild.id
        user_id = message.author.id

        dissociation_active = self._is_dissociation_active(guild_data)
        blackout_active = self._is_blackout_active(guild_data)
        
        guild_data["lives"] = guild_data.get("lives", 3) - 1
        guild_data["failures"] = guild_data.get("failures", 0) + 1
        guild_data["last_fail_user"] = str(user_id)
        
        # Reset user streak
        streaks = guild_data.get("streaks", {})
        streaks[str(user_id)] = 0
        guild_data["streaks"] = streaks
        
        if not blackout_active:
            await self.safe_add_reaction(message, "💀")
        
        # Track whether regression actually changed the expected number.
        try:
            before_current = int(guild_data.get("current_number", 1) or 1)
        except Exception:
            before_current = None

        if guild_data["lives"] <= 0:
            await self.handle_game_over(message, guild_data)
        else:
            # Regression: step the expected number backward (only when not game over).
            try:
                self.apply_regression(guild_data)
            except Exception:
                pass

            try:
                after_current = int(guild_data.get("current_number", 1) or 1)
            except Exception:
                after_current = None

            # Theme deactivation (cosmetic-only): end Blackout if escalation phase drops below 4.
            try:
                if self._is_blackout_active(guild_data):
                    phase_now = self.get_escalation_phase(int(guild_data.get("current_number", 1) or 1))
                    if phase_now < 4:
                        await self._end_blackout_if_active(message.channel, message.channel.id, guild_data)
            except Exception:
                pass

            # Theme deactivation (cosmetic-only): end Permafrost if escalation phase drops below 3.
            try:
                if self._is_permafrost_active(guild_data):
                    phase_now = self.get_escalation_phase(int(guild_data.get("current_number", 1) or 1))
                    if phase_now < 3:
                        await self._end_permafrost_if_active(message.channel, message.channel.id, guild_data)
            except Exception:
                pass

            channel_id = message.channel.id
            if dissociation_active:
                await self._maybe_dissociation_delay(guild_data)
                lives = guild_data.get("lives", 0)
                if self.is_silent_fail(guild_data):
                    await self._send_and_remember(message.channel, channel_id, f"INCORRECT. LIVES: {lives}.", "announce")
                else:
                    if self.is_regression(guild_data):
                        await self._send_and_remember(
                            message.channel,
                            channel_id,
                            f"INCORRECT. NEXT: `{guild_data.get('current_number', 1)}`. LIVES: {lives}.",
                            "announce",
                        )
                    else:
                        await self._send_and_remember(
                            message.channel,
                            channel_id,
                            f"INCORRECT. EXPECTED: `{expected}`. LIVES: {lives}.",
                            "announce",
                        )
            else:
                if self.is_silent_fail(guild_data):
                    await self._send_and_remember(
                        message.channel,
                        channel_id,
                        (
                            f"LIVES REMAINING: {guild_data['lives']}"
                            if blackout_active
                            else f"❌ Lives remaining: {guild_data['lives']}"
                        ),
                        "announce",
                    )
                else:
                    if self.is_regression(guild_data):
                        await self._send_and_remember(
                            message.channel,
                            channel_id,
                            (
                                f"WRONG NUMBER. COUNT REGRESSED TO `{guild_data.get('current_number', 1)}`.\n"
                                f"LIVES REMAINING: {guild_data['lives']}"
                                if blackout_active
                                else f"❌ Wrong number! Count regressed to `{guild_data.get('current_number', 1)}`.\n"
                                     f"Lives remaining: {guild_data['lives']}"
                            ),
                            "announce",
                        )
                    else:
                        await self._send_and_remember(
                            message.channel,
                            channel_id,
                            (
                                f"WRONG NUMBER. EXPECTED: `{expected}`.\nLIVES REMAINING: {guild_data['lives']}"
                                if blackout_active
                                else f"❌ Wrong number! Expected: `{expected}`, got: `{message.content}`\n"
                                     f"Lives remaining: {guild_data['lives']}"
                            ),
                            "announce",
                        )

            # Confusion guide: explain what rule/settings caused the failure/regression.
            try:
                await self._maybe_send_confusion_guide(
                    message,
                    reason="wrong_number",
                    expected=expected,
                    got=got,
                    before_current=before_current,
                    after_current=after_current,
                )
            except Exception:
                pass
        
        self.data_manager.save_guild_data(guild_id, guild_data)

    def _build_confusion_guide_text(
        self,
        reason: str,
        guild_data: dict,
        expected: Optional[int],
        got: Optional[int],
        before_current: Optional[int],
        after_current: Optional[int],
    ) -> str:
        difficulty = (guild_data.get("difficulty_mode") or "normal").lower().strip()
        profile = DIFFICULTY_PROFILES.get(difficulty) or DIFFICULTY_PROFILES.get("normal") or {}

        # Primary explanation per failure type
        lines: List[str] = []
        if reason == "no_consecutive":
            lines.append("Rule Triggered: **No Consecutive** — the same user can’t count twice in a row.")
        elif reason == "wrong_number":
            if difficulty == "bringushell":
                rr = int(profile.get("random_range", 2) or 2)
                lines.append(f"Mode: **Bringushell** — expected number can be random within ±{rr}.")
            elif difficulty == "nightmare":
                skip_pct = float(profile.get("skip_chance", 0.1) or 0.1) * 100.0
                rr = int(profile.get("random_range", 3) or 3)
                lines.append(f"Mode: **Nightmare** — may skip ahead ({skip_pct:.0f}% chance) by 1–{rr}.")
            else:
                lines.append("Rule: **Sequential counting** — expected is the current count.")

            # Silent fail behavior: explain why the bot might not show expected.
            if self.is_silent_fail(guild_data):
                lines.append("Variator: **Silent Fail** — expected value is intentionally hidden.")

            # Regression behavior: explain why the count moved.
            if self.is_regression(guild_data):
                step = int(profile.get("regression_step", 1) or 1)
                if before_current is not None and after_current is not None and after_current != before_current:
                    lines.append(f"Variator: **Regression** — mistake moved the count back by {step}.")
                else:
                    lines.append(f"Variator: **Regression** — on mistakes, the count may move back by {step}.")

        # Add a short Easterman flavor line (briefing/poster), but keep it compact.
        flavor = ""
        try:
            briefing_tables = list(MURKOFF_BRIEFINGS.values())
            if briefing_tables:
                flavor = get_murkoff_line(random.choice(briefing_tables))
        except Exception:
            flavor = ""

        if not flavor:
            flavor = get_murkoff_line(MURKOFF_POSTERS)
        if flavor:
            lines.append(f"Dr. Hendrick Joliet Easterman: {flavor}")
        else:
            lines.append("Dr. Hendrick Joliet Easterman: Maintain protocol. Observe the active rules.")

        return "\n".join(lines).strip()

    async def _maybe_send_confusion_guide(
        self,
        message: discord.Message,
        reason: str,
        expected: Optional[int],
        got: Optional[int],
        before_current: Optional[int],
        after_current: Optional[int],
    ) -> None:
        if not getattr(self, "COUNTING_CONFUSION_GUIDE", True):
            return

        guild = message.guild
        if guild is None:
            return

        try:
            guild_id = int(guild.id)
        except Exception:
            return

        try:
            guild_data = self.data_manager.load_guild_data(guild_id)
        except Exception:
            return

        # Avoid adding extra chatter during Blackout / Dissociation (intentionally confusing).
        try:
            if self._is_blackout_active(guild_data):
                return
            if self._is_dissociation_active(guild_data):
                return
        except Exception:
            return

        cooldown = float(getattr(self, "COUNTING_CONFUSION_GUIDE_COOLDOWN", 20.0) or 20.0)
        key = f"guide:{guild_id}:{message.channel.id}:{reason}"
        now_ts = float(time.monotonic())
        last = self._recent_announcements.get(key)
        if last is not None and (now_ts - float(last)) < cooldown:
            return

        text = self._build_confusion_guide_text(
            reason=reason,
            guild_data=guild_data,
            expected=expected,
            got=got,
            before_current=before_current,
            after_current=after_current,
        )
        if not text:
            return

        self._recent_announcements[key] = now_ts
        await message.channel.send(text)

    async def handle_correct_count(self, message, number: int, guild_data: dict):
        """Handle correct counting attempt"""
        guild_id = message.guild.id
        user_id = message.author.id

        dissociation_active = self._is_dissociation_active(guild_data)
        blackout_active_pre = self._is_blackout_active(guild_data)
        
        # Timing for speed achievements
        now = datetime.datetime.utcnow()
        prev_ts = guild_data.get("last_count_timestamp")
        elapsed = None
        if isinstance(prev_ts, str):
            try:
                prev_dt = datetime.datetime.fromisoformat(prev_ts)
                elapsed = (now - prev_dt).total_seconds()
            except Exception:
                elapsed = None
        
        # Update guild data
        guild_data["last_user_id"] = user_id
        guild_data["current_number"] = number + 1
        guild_data["last_count_timestamp"] = now.isoformat()

        # Flavor-only Murkoff announcement when escalation phase increases.
        try:
            new_phase = self.get_escalation_phase(int(guild_data.get("current_number", 1) or 1))
            previous_phase_raw = guild_data.get("last_phase", None)
            if previous_phase_raw is None:
                guild_data["last_phase"] = new_phase
            else:
                try:
                    previous_phase = int(previous_phase_raw)
                except Exception:
                    previous_phase = new_phase

                if (not dissociation_active) and (not blackout_active_pre) and new_phase > previous_phase:
                    line = get_murkoff_line(MURKOFF_MESSAGES.get("phase_up", []))
                    if line:
                        await self._send_and_remember(message.channel, message.channel.id, line, "murkoff")

                guild_data["last_phase"] = new_phase
        except Exception:
            pass

        # Theme activation (cosmetic-only): Permafrost
        # Constraints:
        # - difficulty == "variortus"
        # - escalation phase >= 3
        # - no theme currently active (no stacking)
        try:
            difficulty_for_theme = (guild_data.get("difficulty_mode") or "normal").lower()
            phase_for_theme = self.get_escalation_phase(int(guild_data.get("current_number", 1) or 1))
            if (difficulty_for_theme == "variortus") and (phase_for_theme >= 3) and (not self._get_active_theme(guild_data)):
                guild_data["active_theme"] = "permafrost"
                guild_data["theme_started_at"] = float(time.time())
                codename = MURKOFF_CODENAMES.get("permafrost", "PERMAFROST")
                line = get_murkoff_line(MURKOFF_MESSAGES.get("event_start", []))
                await self._send_and_remember(
                    message.channel,
                    message.channel.id,
                    f"**{codename}**\n{line}" if line else f"**{codename}**",
                    "murkoff",
                )
        except Exception:
            pass

        # Theme activation (cosmetic-only): Blackout
        # Constraints:
        # - difficulty == "variortus"
        # - escalation phase >= 4
        # - no theme currently active (no stacking)
        try:
            if (difficulty_for_theme == "variortus") and (phase_for_theme >= 4) and (not self._get_active_theme(guild_data)):
                guild_data["active_theme"] = "blackout"
                guild_data["theme_started_at"] = float(time.time())
                codename = MURKOFF_CODENAMES.get("blackout", "BLACKOUT")
                line = get_murkoff_line(MURKOFF_MESSAGES.get("event_start", []))
                await self._send_and_remember(
                    message.channel,
                    message.channel.id,
                    f"**{codename}**\n{line}" if line else f"**{codename}**",
                    "murkoff",
                )
        except Exception:
            pass

        # Theme deactivation (cosmetic-only): end Permafrost if escalation phase drops below 3.
        try:
            if self._is_permafrost_active(guild_data) and (phase_for_theme < 3):
                await self._end_permafrost_if_active(message.channel, message.channel.id, guild_data)
        except Exception:
            pass

        # Theme deactivation (cosmetic-only): end Blackout if escalation phase drops below 4.
        try:
            if self._is_blackout_active(guild_data) and (phase_for_theme < 4):
                await self._end_blackout_if_active(message.channel, message.channel.id, guild_data)
        except Exception:
            pass

        permafrost_active = self._is_permafrost_active(guild_data)
        blackout_active = self._is_blackout_active(guild_data)

        # Event trigger (state only; no enforcement yet).
        # Selection flow:
        # 1) If count % 25 == 0
        # 2) If no event is active
        # 3) Roll once using event_chance
        # 4) Choose which event to start (Countdown OR RL/GL)
        # 5) Start only that event
        try:
            if number % 25 == 0:
                difficulty = (guild_data.get("difficulty_mode") or "normal").lower()
                profile = DIFFICULTY_PROFILES.get(difficulty) or DIFFICULTY_PROFILES.get("normal") or {}
                event_chance = float(profile.get("event_chance", 0.0) or 0.0)

                countdown_active = bool(guild_data.get("countdown_active", False))

                # Passive expiration cleanup so the event doesn't stay stuck on forever.
                rlgl_active = bool(guild_data.get("rlgl_active", False))
                if rlgl_active:
                    try:
                        if await self._end_rlgl_if_expired(message.channel, message.channel.id, guild_data):
                            rlgl_active = False
                    except Exception:
                        pass

                any_event_active = countdown_active or rlgl_active
                if (not any_event_active) and event_chance > 0.0 and random.random() < event_chance:
                    # Choose exactly one event. Do not evaluate the other.
                    chosen = "countdown" if random.random() < 0.5 else "rlgl"

                    if chosen == "countdown":
                        guild_data["countdown_active"] = True
                        guild_data["countdown_user_id"] = int(user_id)
                        guild_data["countdown_expires_at"] = float(time.time() + 10.0)

                        codename = MURKOFF_CODENAMES.get("countdown", "COUNTDOWN")
                        line = get_murkoff_line(MURKOFF_MESSAGES.get("event_start", []))
                        await self._send_and_remember(
                            message.channel,
                            message.channel.id,
                            f"**{codename}**\n{line}" if line else f"**{codename}**",
                            "murkoff",
                        )
                    else:
                        guild_data["rlgl_active"] = True
                        guild_data["rlgl_state"] = "red"
                        guild_data["rlgl_expires_at"] = float(time.time() + 10.0)

                        codename = MURKOFF_CODENAMES.get("red_light", "RED LIGHT")
                        await self._send_and_remember(
                            message.channel,
                            message.channel.id,
                            f"**{codename}**\nHALT.",
                            "murkoff",
                        )
        except Exception:
            pass
        
        # Update user stats
        count_stats = guild_data.get("count_stats", {})
        count_stats[str(user_id)] = count_stats.get(str(user_id), 0) + 1
        guild_data["count_stats"] = count_stats
        
        # Update streaks
        streaks = guild_data.get("streaks", {})
        streaks[str(user_id)] = streaks.get(str(user_id), 0) + 1
        
        # Check for highest streak
        if streaks[str(user_id)] > guild_data.get("highest_streak", 0):
            guild_data["highest_streak"] = streaks[str(user_id)]
            guild_data["highest_streak_user"] = str(user_id)
        
        guild_data["streaks"] = streaks
        
        # Update simple daily stat counter per user without changing existing schema drastically
        try:
            date_key = now.date().isoformat()
            daily_stats = guild_data.get("daily_stats", {})
            per_user = daily_stats.get(date_key, {})
            per_user[str(user_id)] = int(per_user.get(str(user_id), 0) or 0) + 1
            daily_stats[date_key] = per_user
            guild_data["daily_stats"] = daily_stats
        except Exception:
            pass
        
        limited_hud_active = self.is_limited_hud(guild_data) or dissociation_active
        if (not limited_hud_active) and (not permafrost_active) and (not blackout_active):
            await self.safe_add_reaction(message, "✅")
        
        # Pattern fun (limited spam): announce one primary pattern and add small reactions
        # Suppress extra pattern messages if this number is already a fixed special
        if (not dissociation_active) and (not permafrost_active) and (not blackout_active):
            try:
                await self.detect_and_announce_patterns(
                    message,
                    number,
                    suppress_message=(number in self.special_numbers) or limited_hud_active,
                )
            except Exception:
                pass
        
        # Check achievements using counted number, not incremented current_number
        current_stats = {
            "total_counts": count_stats.get(str(user_id), 0),
            "current_streak": streaks.get(str(user_id), 0)
        }
        new_achievements = CountingAchievements.check_achievements(
            user_id=user_id,
            guild_data=guild_data,
            current_stats=current_stats,
            counted_number=number,
            now=now,
            elapsed_seconds=elapsed,
        )
        
        # Daily target mini-game: award and announce when hit
        try:
            extra_daily = await self.handle_daily_target_hit(
                message,
                number,
                guild_data,
                now,
                suppress_announce=dissociation_active or permafrost_active,
            )
            if extra_daily:
                new_achievements.extend(extra_daily)
        except Exception:
            pass
        
        if new_achievements and (not dissociation_active) and (not permafrost_active) and (not blackout_active):
            # Build a dedupe key for this announcement
            ach_key = f"ach:{message.guild.id}:{message.channel.id}:{user_id}:{number}:{','.join(sorted(new_achievements))}"
            now_ts = time.monotonic()
            last = self._recent_announcements.get(ach_key)
            if last is None or (now_ts - last) > self.ANNOUNCE_DEDUP_WINDOW:
                await self.announce_achievements(message.channel, user_id, new_achievements)
                # Record and prune
                self._recent_announcements[ach_key] = now_ts
                if len(self._recent_announcements) > 10000:
                    # Remove oldest ~100 entries quickly
                    for _ in range(100):
                        try:
                            self._recent_announcements.pop(next(iter(self._recent_announcements)))
                        except Exception:
                            break
        
        # Announce special numbers directly in channel
        if (not dissociation_active) and (not blackout_active) and (number in self.special_numbers):
            spec_key = f"spec:{message.guild.id}:{message.channel.id}:{number}"
            now_ts = time.monotonic()
            last = self._recent_announcements.get(spec_key)
            if last is None or (now_ts - last) > self.ANNOUNCE_DEDUP_WINDOW:
                if permafrost_active:
                    await self._maybe_permafrost_delay(guild_data)
                    await self._send_and_remember(
                        message.channel,
                        message.channel.id,
                        f"SPECIAL VALUE LOGGED: {number}.",
                        "murkoff",
                    )
                else:
                    quote = random.choice(self.special_numbers[number])
                    await self._send_and_remember(
                        message.channel,
                        message.channel.id,
                        f"🎉 **Special Number {number}**\n{quote}",
                        "announce",
                    )
                self._recent_announcements[spec_key] = now_ts
        
        # Check for milestones
        if (not blackout_active) and (number % 100 == 0):
            if dissociation_active:
                await self._maybe_dissociation_delay(guild_data)
                await self._send_and_remember(
                    message.channel,
                    message.channel.id,
                    f"MILESTONE LOGGED: {number}.",
                    "announce",
                )
            elif permafrost_active:
                await self._maybe_permafrost_delay(guild_data)
                await self._send_and_remember(
                    message.channel,
                    message.channel.id,
                    f"MILESTONE LOGGED: {number}.",
                    "murkoff",
                )
            else:
                embed = discord.Embed(
                    title=f"🎉 Milestone Reached: {number}!",
                    description=f"Congratulations to <@{user_id}> for reaching {number}!",
                    color=discord.Color.gold()
                )
                view = CountingView(self, guild_id)
                await message.channel.send(embed=embed, view=view)

        if not blackout_active:
            # Cosmetic dissociation messaging (does not affect gameplay).
            await self._maybe_send_dissociation_line(message, guild_data)

            # Cosmetic deja-vu messaging (does not affect gameplay).
            await self._maybe_send_dejavu_line(message, guild_data)

            # Cosmetic psychotic messaging (does not affect gameplay).
            await self._maybe_send_paranoia_line(message, guild_data)
        
        self.data_manager.save_guild_data(guild_id, guild_data)

    async def handle_game_over(self, message, guild_data: dict):
        """Handle game over scenario"""
        guild_id = message.guild.id

        blackout_active = self._is_blackout_active(guild_data)

        # Theme deactivation (cosmetic-only): reset ends Blackout.
        try:
            await self._end_blackout_if_active(message.channel, message.channel.id, guild_data)
        except Exception:
            pass

        # Theme deactivation (cosmetic-only): reset ends Permafrost.
        try:
            await self._end_permafrost_if_active(message.channel, message.channel.id, guild_data)
        except Exception:
            pass

        dissociation_active = self._is_dissociation_active(guild_data)
        if blackout_active:
            description = "FAILURE CONDITION MET."
        elif dissociation_active:
            await self._maybe_dissociation_delay(guild_data)
            description = "FAILURE CONDITION MET."
        else:
            fail_quote = random.choice(self.special_numbers[-1])
            description = f"**Jon (Bringus) says:** \"{fail_quote}\""

        embed = discord.Embed(
            title=("GAME OVER" if blackout_active else "💀 GAME OVER"),
            description=description,
            color=discord.Color.red()
        )
        embed.add_field(
            name=("Final Stats" if blackout_active else "📊 Final Stats"),
            value=f"Reached: {guild_data.get('current_number', 1) - 1}\nTotal Failures: {guild_data.get('failures', 0)}",
            inline=False
        )
        
        # Reset game
        guild_data.update({
            "current_number": 1,
            "lives": 3,
            "last_user_id": None,
            "last_reset": datetime.datetime.utcnow().isoformat()
        })
        
        # Reset all streaks
        streaks = guild_data.get("streaks", {})
        for user_id in streaks:
            streaks[user_id] = 0
        guild_data["streaks"] = streaks
        
        await message.channel.send(embed=embed)

    async def announce_achievements(self, channel, user_id: int, achievements: List[str]):
        """Announce new achievements"""
        # Blackout theme: suppress non-essential celebratory messages.
        try:
            guild_data = self.data_manager.load_guild_data(channel.guild.id)
            if self._is_blackout_active(guild_data):
                return
        except Exception:
            pass

        embed = discord.Embed(
            title="🏆 Achievement Unlocked!",
            color=discord.Color.gold()
        )
        
        # Cap to avoid hitting 25-field limit; summarize extras
        max_fields = 10
        shown = 0
        for achievement_id in achievements:
            if shown >= max_fields:
                break
            achievement = CountingAchievements.ACHIEVEMENTS[achievement_id]
            embed.add_field(
                name=f"{achievement['emoji']} {achievement['name']}",
                value=achievement['description'],
                inline=False
            )
            shown += 1
        extra = len(achievements) - shown
        if extra > 0:
            embed.add_field(
                name="… and more",
                value=f"+{extra} additional achievement(s) unlocked",
                inline=False
            )
        
        member = channel.guild.get_member(user_id)
        display_name = member.display_name if member else "Unknown User"
        embed.set_footer(text=f"Congratulations {display_name}!")
        await channel.send(embed=embed)

    async def create_stats_embed(self, guild_id: int, user_id: Optional[int] = None) -> discord.Embed:
        """Create statistics embed"""
        guild_data = self.data_manager.load_guild_data(guild_id)
        
        embed = discord.Embed(
            title="📊 Counting Statistics",
            color=discord.Color.blue()
        )
        
        # Global stats
        embed.add_field(
            name="🌍 Global Stats",
            value=f"Current Number: {guild_data.get('current_number', 1)}\n"
                  f"Lives: {guild_data.get('lives', 3)}\n"
                  f"Total Failures: {guild_data.get('failures', 0)}",
            inline=True
        )
        
        # User stats
        if user_id:
            count_stats = guild_data.get("count_stats", {})
            streaks = guild_data.get("streaks", {})
            user_counts = count_stats.get(str(user_id), 0)
            user_streak = streaks.get(str(user_id), 0)
            
            embed.add_field(
                name="👤 Your Stats",
                value=f"Total Counts: {user_counts}\n"
                      f"Current Streak: {user_streak}\n"
                      f"Best Streak: {guild_data.get('highest_streak', 0) if str(user_id) == guild_data.get('highest_streak_user') else 'N/A'}",
                inline=True
            )
        
        # Difficulty info
        difficulty = guild_data.get("difficulty_mode", "normal")
        channel_id = guild_data.get("channel_id")
        channel_mention = f"<#{channel_id}>" if channel_id else "Not Set"
        
        embed.add_field(
            name="⚙️ Settings",
            value=f"Difficulty: {difficulty.title()}\n"
                  f"Channel: {channel_mention}",
            inline=True
        )
        
        return embed

    async def detect_and_announce_patterns(self, message: discord.Message, number: int, suppress_message: bool = False):
        """Detect fun number patterns and optionally announce one primary message.
        Always adds lightweight reactions; uses dedupe to avoid repeats.
        """
        if not message.guild:
            return
        s = str(number)
        guild_id = message.guild.id
        channel_id = message.channel.id
        now_ts = time.monotonic()

        limited_hud_active = False

        # Respect per-user difficulty preferences in 'per-user' scope
        try:
            guild_data = self.data_manager.load_guild_data(guild_id)
            if self._is_blackout_active(guild_data):
                return
            limited_hud_active = self.is_limited_hud(guild_data)
            if limited_hud_active:
                suppress_message = True
            if guild_data.get("difficulty_scope") == "per-user":
                user_modes = guild_data.get("user_difficulties", {})
                mode = user_modes.get(str(message.author.id))
                if mode == "zen":
                    suppress_message = True
                elif mode == "chaos":
                    suppress_message = False
        except Exception:
            pass

        def dedup(key: str) -> bool:
            last = self._recent_announcements.get(key)
            if last is None or (now_ts - last) > self.ANNOUNCE_DEDUP_WINDOW:
                self._recent_announcements[key] = now_ts
                return True
            return False

        # Determine patterns
        is_repeater = len(s) >= 3 and all(ch == s[0] for ch in s)
        is_pal = len(s) >= 3 and s == s[::-1]
        is_up = len(s) >= 3 and all(int(s[i]) + 1 == int(s[i+1]) for i in range(len(s)-1))
        is_down = len(s) >= 3 and all(int(s[i]) - 1 == int(s[i+1]) for i in range(len(s)-1))
        r = int(number ** 0.5)
        is_square = number >= 25 and r * r == number
        # Fibonacci & Armstrong detection (lightweight) for reactions only
        def is_fibonacci_local(n: int) -> bool:
            if n < 0 or n > 1_000_000:
                return False
            def is_ps(x: int) -> bool:
                q = int(x ** 0.5)
                return q*q == x
            return is_ps(5*n*n + 4) or is_ps(5*n*n - 4)
        def is_armstrong_local(n: int) -> bool:
            if n < 100:
                return False
            st = str(n)
            p = len(st)
            return sum((ord(c)-48) ** p for c in st) == n
        is_fib = is_fibonacci_local(number)
        is_armstrong = is_armstrong_local(number)

        # Prime reaction only (low-spam)
        if (not limited_hud_active) and number <= 2000:
            n = number
            prime = False
            if n > 1:
                if n in (2, 3):
                    prime = True
                elif n % 2 != 0 and n % 3 != 0:
                    i = 5
                    prime = True
                    while i * i <= n:
                        if n % i == 0 or n % (i + 2) == 0:
                            prime = False
                            break
                        i += 6
            if prime:
                try:
                    await self.safe_add_reaction(message, "🔹")
                except Exception:
                    pass
        # Calculus/math extras
        def is_cube_local(n: int) -> bool:
            if n < 27:
                return False
            q = int(round(n ** (1/3)))
            for k in (q-1, q, q+1):
                if k > 0 and k*k*k == n:
                    return True
            return False
        def is_factorial_local(n: int) -> bool:
            f = 1
            k = 1
            while f < n and k <= 12:
                k += 1
                f *= k
            return f == n and k >= 3
        def is_triangular_local(n: int) -> bool:
            x = 8*n + 1
            r2 = int(x ** 0.5)
            return r2*r2 == x
        is_cube = is_cube_local(number)
        is_factorial = is_factorial_local(number)
        is_triangular = is_triangular_local(number)

        # Primary announcement priority
        primary_msg = None
        primary_key = None
        if is_repeater:
            primary_msg = f"🔁 Repdigit! {number} is the same digit repeated."
            primary_key = f"pat:rep:{guild_id}:{channel_id}:{number}"
        elif is_pal:
            primary_msg = f"🪞 Palindrome! {number} reads the same backward and forward."
            primary_key = f"pat:pal:{guild_id}:{channel_id}:{number}"
        elif is_up:
            primary_msg = f"⏫ Ascending sequence detected: {number}."
            primary_key = f"pat:up:{guild_id}:{channel_id}:{number}"
        elif is_down:
            primary_msg = f"⏬ Descending sequence detected: {number}."
            primary_key = f"pat:down:{guild_id}:{channel_id}:{number}"
        elif is_square:
            primary_msg = f"◼️ Perfect square! {r}² = {number}."
            primary_key = f"pat:sq:{guild_id}:{channel_id}:{number}"
        elif is_cube:
            primary_msg = f"🧊 Perfect cube! {number} = {int(round(number ** (1/3)))}³."
            primary_key = f"pat:cube:{guild_id}:{channel_id}:{number}"
        elif is_fib:
            primary_msg = f"🌀 Fibonacci number spotted: {number}."
            primary_key = f"pat:fib:{guild_id}:{channel_id}:{number}"
        elif is_armstrong:
            primary_msg = f"💎 Armstrong (narcissistic) number! {number} shines by its own digits."
            primary_key = f"pat:arms:{guild_id}:{channel_id}:{number}"

        # Add small pattern reactions regardless
        try:
            if limited_hud_active:
                return
            if is_repeater:
                await self.safe_add_reaction(message, "🔁")
            if is_pal:
                await self.safe_add_reaction(message, "🔂")
            if is_up:
                await self.safe_add_reaction(message, "⏫")
            if is_down:
                await self.safe_add_reaction(message, "⏬")
            if is_square:
                await self.safe_add_reaction(message, "◼️")
            if is_cube:
                await self.safe_add_reaction(message, "🧊")
            if is_triangular:
                await self.safe_add_reaction(message, "🔺")
            if is_factorial:
                await self.safe_add_reaction(message, "🧮")
            if is_fib:
                await self.safe_add_reaction(message, "🌀")
            if is_armstrong:
                await self.safe_add_reaction(message, "💎")
        except Exception:
            pass

        # Only send one message (and none if suppressed)
        if primary_msg and primary_key and (not suppress_message) and dedup(primary_key):
            await self._send_and_remember(message.channel, message.channel.id, primary_msg, "announce")

    def _get_or_roll_daily_target(self, guild_id: int, guild_data: dict, now: datetime.datetime) -> dict:
        """Get or roll today's Daily Star target.
        Reworked: now supports difficulty-based multi-digit targets and per-channel isolation.
        Schema migrated lazily to preserve backward compatibility.
        Fields:
          date: YYYY-MM-DD
          digits: list[int] (the required ending sequence, e.g. [4] or [2,5])
          length: len(digits)
          channel_id: optional channel scoping (None = global)
          winner_user_id: first user who hits target
        """
        date_key = now.date().isoformat()
        legacy = guild_data.get("daily_target") or {}
        # Migrate legacy structure (last_digit)
        if "last_digit" in legacy and "digits" not in legacy:
            ld = legacy.get("last_digit")
            legacy = {
                "date": legacy.get("date"),
                "digits": [int(ld)] if ld is not None else [],
                "length": 1 if ld is not None else 0,
                "channel_id": None,
                "winner_user_id": legacy.get("winner_user_id")
            }
        target = legacy
        # Reroll if stale or malformed
        if target.get("date") != date_key or not target.get("digits"):
            difficulty = (guild_data.get("difficulty_mode") or "normal").lower()
            scope_len = 1
            if difficulty in ("hard", "nightmare"):
                scope_len = 2
            if difficulty == "bringushell":
                scope_len = 3
            seed = int(f"{guild_id}{date_key.replace('-', '')}{scope_len}")
            rng = random.Random(seed)
            digits = [rng.randint(0,9) for _ in range(scope_len)]
            target = {
                "date": date_key,
                "digits": digits,
                "length": scope_len,
                "channel_id": None,
                "winner_user_id": None
            }
            guild_data["daily_target"] = target
        return target

    async def handle_daily_target_hit(
        self,
        message: discord.Message,
        number: int,
        guild_data: dict,
        now: datetime.datetime,
        suppress_announce: bool = False,
    ) -> List[str]:
        if not message.guild:
            return []
        target = self._get_or_roll_daily_target(message.guild.id, guild_data, now)
        if target.get("winner_user_id"):
            return []
        digits: List[int] = target.get("digits") or []
        length = int(target.get("length") or len(digits))
        if not digits or length == 0:
            return []
        # Convert number to string and compare trailing sequence
        s = str(number)
        if len(s) < length:
            return []
        trailing = [int(ch) for ch in s[-length:]]
        if trailing == digits:
            target["winner_user_id"] = str(message.author.id)
            seq_str = "".join(str(d) for d in digits)
            key = f"daily:{message.guild.id}:{message.channel.id}:{target['date']}:{seq_str}"
            now_ts = time.monotonic()
            last = self._recent_announcements.get(key)
            if last is None or (now_ts - last) > self.ANNOUNCE_DEDUP_WINDOW:
                if not suppress_announce:
                    await self._send_and_remember(
                        message.channel,
                        message.channel.id,
                        f"🌟 Daily Star! <@{message.author.id}> hit today's target (ends with {seq_str}).",
                        "announce",
                    )
                self._recent_announcements[key] = now_ts
            ach = guild_data.get("achievements", {})
            arr = ach.get(str(message.author.id), [])
            added = []
            if "daily_star" not in arr:
                arr.append("daily_star")
                added.append("daily_star")
            ach[str(message.author.id)] = arr
            guild_data["achievements"] = ach
            return added
        return []

    async def create_achievements_embed(self, guild_id: int, user_id: int) -> discord.Embed:
        """Create achievements embed for a user (grouped to stay under 25 fields)"""
        guild_data = self.data_manager.load_guild_data(guild_id)
        achievements = guild_data.get("achievements", {})
        user_achievements = set(achievements.get(str(user_id), []))
        total = len(CountingAchievements.ACHIEVEMENTS)
        unlocked = len(user_achievements)
        
        embed = discord.Embed(
            title=f"🏆 Achievements ({unlocked}/{total})",
            color=discord.Color.gold()
        )
        
        # Categorize achievements by key prefix
        def lines_for(keys):
            parts = []
            for k in keys:
                a = CountingAchievements.ACHIEVEMENTS[k]
                status = "✅" if k in user_achievements else "❌"
                parts.append(f"{status} {a['emoji']} {a['name']}")
            return "\n".join(parts) or "None"
        
        ach_keys = list(CountingAchievements.ACHIEVEMENTS.keys())
        streak_keys = sorted([k for k in ach_keys if k.startswith("streak_")], key=lambda x: int(x.split("_")[1]))
        count_keys = sorted([k for k in ach_keys if k.startswith("count_")], key=lambda x: int(x.split("_")[1]))
        milestone_keys = sorted([k for k in ach_keys if k.startswith("milestone_")], key=lambda x: int(x.split("_")[1]))
        special_keys = [k for k in ach_keys if k not in streak_keys + count_keys + milestone_keys]
        
        # Build grouped fields (max 4 fields)
        embed.add_field(name="🔥 Streaks", value=lines_for(streak_keys)[:1024], inline=False)
        embed.add_field(name="🧮 Counts", value=lines_for(count_keys)[:1024], inline=False)
        embed.add_field(name="🎯 Milestones", value=lines_for(milestone_keys)[:1024], inline=False)
        embed.add_field(name="✨ Specials", value=lines_for(special_keys)[:1024], inline=False)
        
        return embed

    async def create_leaderboard_embed(self, guild_id: int) -> discord.Embed:
        """Create leaderboard embed"""
        guild_data = self.data_manager.load_guild_data(guild_id)
        count_stats = guild_data.get("count_stats", {})
        
        # Sort by count
        sorted_stats = sorted(count_stats.items(), key=lambda x: x[1], reverse=True)[:10]
        
        embed = discord.Embed(
            title="📈 Counting Leaderboard",
            color=discord.Color.green()
        )
        
        leaderboard_text = ""
        for i, (user_id, count) in enumerate(sorted_stats, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            leaderboard_text += f"{medal} <@{user_id}> - {count} counts\n"
        
        embed.description = leaderboard_text or "No data yet!"
        
        return embed

    async def create_info_embed(self, guild_id: int) -> discord.Embed:
        """Create info embed about the counting game"""
        guild_data = self.data_manager.load_guild_data(guild_id)
        
        embed = discord.Embed(
            title="ℹ️ Counting Game Info",
            description="Welcome to the Optical Media Counting Challenge!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🎯 Rules",
            value="• Count sequentially starting from 1\n"
                  "• No counting twice in a row\n"
                  "• Wrong numbers lose lives\n"
                  "• Game resets when lives reach 0\n"
                  "• Some rules vary by difficulty (see Variators)",
            inline=False
        )
        
        scope = guild_data.get("difficulty_scope", "global")
        global_mode = guild_data.get("difficulty_mode", "normal").title()
        embed.add_field(
            name="🎮 Difficulty",
            value=(
                f"Scope: **{scope}**\n"
                f"Global Mode: **{global_mode}**\n\n"
                "Per-user overlays (when scope=per-user):\n"
                "• classic: default extras\n"
                "• zen: suppress pattern messages\n"
                "• chaos: always allow pattern messages"
            ),
            inline=False
        )

        # Variators: plain-language explanations of the rule toggles used by difficulty profiles.
        mode_key = (guild_data.get("difficulty_mode") or "normal").lower().strip()
        profile = DIFFICULTY_PROFILES.get(mode_key) or DIFFICULTY_PROFILES.get("normal") or {}

        def _on_off(flag: Any) -> str:
            return "ON" if bool(flag) else "OFF"

        variators_explainer = (
            "These are rule toggles the current difficulty mode can change:\n"
            "• **No Consecutive**: same user can’t count twice in a row\n"
            "• **Silent Fail**: wrong-count feedback won’t reveal the expected number\n"
            "• **Regression**: after a mistake (non-game-over), the expected number moves backward\n"
            "• **Limited HUD**: fewer helpful confirmations/callouts (silence can be intentional)\n"
            "• **Events**: chance at every 25th count to trigger a special event"
        )

        # Current profile snapshot (keep compact so it fits in an embed field).
        regression_step = int(profile.get("regression_step", 1) or 1)
        random_range = int(profile.get("random_range", 0) or 0)
        skip_pct = float(profile.get("skip_chance", 0.0) or 0.0) * 100.0
        current_profile = (
            f"Current profile (**{global_mode}**):\n"
            f"• No Consecutive: **{_on_off(profile.get('no_consecutive', True))}**\n"
            f"• Silent Fail: **{_on_off(profile.get('silent_fail', True))}**\n"
            f"• Regression: **{_on_off(profile.get('regression', True))}** (step **{regression_step}**)\n"
            f"• Limited HUD: **{_on_off(profile.get('limited_hud', False))}**\n"
            f"• Events: **{_on_off(float(profile.get('event_chance', 0.0) or 0.0) > 0.0)}**\n"
            f"• Skip Chance: **{skip_pct:.0f}%**\n"
            f"• Random Range: **±{random_range}**"
        )

        embed.add_field(
            name="🧩 Variators",
            value=f"{variators_explainer}\n\n{current_profile}",
            inline=False,
        )
        
        embed.add_field(
            name="🏆 Features",
            value="• Achievement system\n"
                  "• Personal statistics\n"
                  "• Leaderboards\n"
                  "• Special number reactions",
            inline=False
        )
        
        return embed

    async def safe_add_reaction(self, message: discord.Message, emoji: str):
        """Add a reaction with simple per-channel throttling and retry to reduce 429s.
        - Ensures a minimum interval between reactions in the same channel.
        - Retries once on HTTP 429 with backoff.
        """
        try:
            loop_time = asyncio.get_running_loop().time()
        except RuntimeError:
            # Fallback if no running loop context (unlikely here)
            loop_time = 0.0

        channel_id = message.channel.id
        lock = self._reaction_locks.get(channel_id)
        if lock is None:
            lock = self._reaction_locks[channel_id] = Lock()

        async with lock:
            # Throttle based on last reaction time in this channel
            last = self._last_reaction_at.get(channel_id, 0.0)
            delta = loop_time - last
            if delta < self.REACTION_MIN_INTERVAL:
                await asyncio.sleep(self.REACTION_MIN_INTERVAL - delta)

            try:
                await message.add_reaction(emoji)
                # Update last reaction timestamp
                self._last_reaction_at[channel_id] = asyncio.get_running_loop().time()
                return
            except discord.HTTPException as e:
                # If rate limited, wait a bit longer and try once more
                status = getattr(e, "status", None)
                if status == 429:
                    await asyncio.sleep(self.REACTION_MIN_INTERVAL + 0.5)
                    try:
                        await message.add_reaction(emoji)
                        self._last_reaction_at[channel_id] = asyncio.get_running_loop().time()
                    except Exception:
                        # Give up silently to avoid spamming warnings
                        pass
                else:
                    # Non-429 error: ignore to keep the game flowing
                    pass

    @commands.hybrid_command(name="lifes", description="Show current lives and counting progress")
    async def lifes(self, ctx):
        guild_data = self.data_manager.load_guild_data(ctx.guild.id)
        embed = discord.Embed(
            title="🧮 Velvet Room Counting Progress",
            description=f"**Lives Remaining:** {guild_data.get('lives', 3)}\n"
                       f"**Current Number:** {guild_data.get('current_number', 1)}\n"
                       f"**Difficulty:** {guild_data.get('difficulty_mode', 'normal').title()}",
            color=0x1F1E33
        )
        view = CountingView(self, ctx.guild.id)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="countstats", description="Show counting statistics and leaderboard")
    async def countstats(self, ctx):
        embed = await self.create_leaderboard_embed(ctx.guild.id)
        view = CountingView(self, ctx.guild.id)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="testcount", description="Test the next expected number")
    async def testcount(self, ctx):
        guild_data = self.data_manager.load_guild_data(ctx.guild.id)
        expected = self.get_expected_number(guild_data)
        difficulty = guild_data.get("difficulty_mode", "normal")
        
        embed = discord.Embed(
            title="🔍 Next Number Test",
            description=f"Expected: `{expected}`\nDifficulty: {difficulty.title()}",
            color=discord.Color.yellow()
        )
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="resetcount", description="Reset the counting game (admin only)")
    @app_commands.describe(confirm="Type 'confirm' to reset the game")
    async def resetcount(self, ctx, confirm: str = ""):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need Manage Guild permission to reset the game.", ephemeral=True)
            return
        
        if confirm.lower() != "confirm":
            await ctx.send("⚠️ Add `confirm` to the command to reset: `/resetcount confirm`", ephemeral=True)
            return

        # Theme deactivation (cosmetic-only): reset ends Permafrost / Blackout.
        try:
            old_data = self.data_manager.load_guild_data(ctx.guild.id)
            await self._end_permafrost_if_active(ctx.channel, ctx.channel.id, old_data)
            await self._end_blackout_if_active(ctx.channel, ctx.channel.id, old_data)
        except Exception:
            pass
        
        # Snapshot before destructive change
        self._snapshot_guild(ctx.guild.id)
        guild_data = self.data_manager.get_default_guild_data()
        guild_data["channel_id"] = self.data_manager.load_guild_data(ctx.guild.id).get("channel_id")
        self.data_manager.save_guild_data(ctx.guild.id, guild_data)
        
        embed = discord.Embed(
            title="🔁 Game Reset",
            description="The counting game has been completely reset!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="setcountchannel", description="Set the counting channel")
    async def setcountchannel(self, ctx, channel: Optional[discord.TextChannel] = None):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need Manage Guild permission to set the channel.", ephemeral=True)
            return
        
        channel = channel or ctx.channel
        guild_data = self.data_manager.load_guild_data(ctx.guild.id)
        guild_data["channel_id"] = channel.id
        self.data_manager.save_guild_data(ctx.guild.id, guild_data)
        
        embed = discord.Embed(
            title="✅ Channel Set",
            description=f"Counting channel set to {channel.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="setdifficulty", description="Set counting game difficulty")
    async def setdifficulty(self, ctx):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need Manage Guild permission to change difficulty.", ephemeral=True)
            return
        
        modal = DifficultyModal(self, ctx.guild.id)
        await ctx.interaction.response.send_modal(modal)

    @commands.hybrid_command(name="setpersonalguild", description="Mark this guild as personal (separate from global)")
    async def setpersonalguild(self, ctx, enabled: bool = True):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ You need Administrator permission for this command.", ephemeral=True)
            return
        
        guild_id = str(ctx.guild.id)
        if guild_id not in self.guild_configs:
            self.guild_configs[guild_id] = {}
        
        self.guild_configs[guild_id]["is_personal_guild"] = enabled
        self.save_all_guild_configs()
        
        status = "enabled" if enabled else "disabled"
        embed = discord.Embed(
            title=f"🏠 Personal Guild {status.title()}",
            description=f"This guild is now {'isolated from' if enabled else 'part of'} the global counting network.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="achievements", description="View your counting achievements")
    async def achievements(self, ctx, user: Optional[discord.Member] = None):
        user = user or ctx.author
        embed = await self.create_achievements_embed(ctx.guild.id, user.id)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="countinginfo", description="Get information about the counting game")
    async def countinginfo(self, ctx):
        embed = await self.create_info_embed(ctx.guild.id)
        view = CountingView(self, ctx.guild.id)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="dailytarget", description="Show today's Daily Star target")
    async def dailytarget(self, ctx):
        guild_data = self.data_manager.load_guild_data(ctx.guild.id)
        now = datetime.datetime.utcnow()
        target = self._get_or_roll_daily_target(ctx.guild.id, guild_data, now)
        self.data_manager.save_guild_data(ctx.guild.id, guild_data)
        digits = target.get("digits") or []
        winner = target.get("winner_user_id")
        seq_str = "".join(str(d) for d in digits) if digits else "?"
        if len(digits) == 1:
            desc = f"Numbers ending with **{seq_str}** will win today's 🌟 Daily Star."
        else:
            desc = f"Numbers whose last {len(digits)} digits are **{seq_str}** will win today's 🌟 Daily Star."
        diff = guild_data.get("difficulty_mode", "normal").title()
        desc += f"\nDifficulty: **{diff}** (target length {len(digits)})."
        if winner:
            desc += f"\nAlready claimed by <@{winner}>."
        embed = discord.Embed(title="🌟 Daily Target", description=desc, color=discord.Color.gold())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="rerolldailytarget", description="Reroll today's Daily Star target (admin)")
    @app_commands.describe()
    @commands.has_guild_permissions(manage_guild=True)
    async def reroll_dailytarget(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return
        guild_id = ctx.guild.id
        guild_data = self.data_manager.load_guild_data(guild_id)
        # Force reroll by clearing target or shifting date
        now = datetime.datetime.utcnow()
        guild_data["daily_target"] = {"date": None, "digits": [], "length": 0, "channel_id": None, "winner_user_id": None}
        target = self._get_or_roll_daily_target(guild_id, guild_data, now)
        self.data_manager.save_guild_data(guild_id, guild_data)
        seq_str = "".join(str(d) for d in (target.get("digits") or [])) or "?"
        await ctx.send(f"✅ Rerolled today's Daily Star. New target ends with **{seq_str}**.")

    # --- Mobile-friendly helpers ---
    @commands.hybrid_command(name="next", description="Show the next expected number (mobile-friendly)")
    async def next_number(self, ctx):
        data = self.data_manager.load_guild_data(ctx.guild.id)
        expected = self.get_expected_number(data)
        embed = discord.Embed(title="📱 Next Number", description=f"`{expected}`\nLong-press to copy on mobile.", color=discord.Color.dark_blue())
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="mobilehelper", description="Open mobile helper with quick actions")
    async def mobilehelper(self, ctx):
        data = self.data_manager.load_guild_data(ctx.guild.id)
        expected = self.get_expected_number(data)
        view = MobileHelperView(self, ctx.guild.id, expected)
        await ctx.send("Mobile helper opened (ephemeral).", view=view, ephemeral=True)

    @commands.hybrid_command(name="setdifficultyscope", description="Set difficulty scope: global or per-user")
    @app_commands.describe(scope="Choose 'global' to apply one mode to everyone, or 'per-user' to let users pick their own overlays")
    async def setdifficultyscope(self, ctx, scope: str):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need Manage Guild permission to change scope.", ephemeral=True)
            return
        scope = scope.lower().strip()
        if scope not in ("global", "per-user"):
            await ctx.send("Invalid scope. Use 'global' or 'per-user'.", ephemeral=True)
            return
        guild_data = self.data_manager.load_guild_data(ctx.guild.id)
        guild_data["difficulty_scope"] = scope
        self.data_manager.save_guild_data(ctx.guild.id, guild_data)
        await ctx.send(f"✅ Difficulty scope set to **{scope}**.")

    @commands.hybrid_command(name="mydifficulty", description="Set your personal difficulty overlay (per-user scope)")
    @app_commands.describe(mode="Choose: classic, zen, chaos")
    async def mydifficulty(self, ctx, mode: str):
        mode = mode.lower().strip()
        allowed = {"classic", "zen", "chaos"}
        if mode not in allowed:
            await ctx.send("Invalid mode. Options: classic, zen, chaos", ephemeral=True)
            return
        guild_data = self.data_manager.load_guild_data(ctx.guild.id)
        user_modes = guild_data.get("user_difficulties", {})
        user_modes[str(ctx.author.id)] = mode
        guild_data["user_difficulties"] = user_modes
        self.data_manager.save_guild_data(ctx.guild.id, guild_data)
        await ctx.send(f"✅ Your difficulty overlay is now **{mode}**.\nNote: Overlays apply when scope is set to per-user.")

    @commands.hybrid_command(name="showdifficulty", description="Show current difficulty scope and modes")
    async def showdifficulty(self, ctx, user: Optional[discord.Member] = None):
        guild_data = self.data_manager.load_guild_data(ctx.guild.id)
        scope = guild_data.get("difficulty_scope", "global")
        global_mode = guild_data.get("difficulty_mode", "normal")
        user = user or ctx.author
        user_modes = guild_data.get("user_difficulties", {})
        user_mode = user_modes.get(str(user.id), "classic")
        desc = f"Scope: **{scope}**\nGlobal mode: **{global_mode}**"
        if scope == "per-user":
            desc += f"\n{user.mention}'s overlay: **{user_mode}**"
        embed = discord.Embed(title="Difficulty Settings", description=desc, color=discord.Color.blurple())
        await ctx.send(embed=embed)

    # --- Admin: direct state controls ---
    @commands.hybrid_command(name="setlives", description="Set remaining lives (admin)")
    @app_commands.describe(lives="Number of lives (>=0)")
    async def setlives(self, ctx, lives: int):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need Manage Guild permission.", ephemeral=True)
            return
        if lives < 0:
            await ctx.send("Lives must be >= 0.", ephemeral=True)
            return
        self._snapshot_guild(ctx.guild.id)
        data = self.data_manager.load_guild_data(ctx.guild.id)
        data["lives"] = int(lives)
        self.data_manager.save_guild_data(ctx.guild.id, data)
        await ctx.send(f"✅ Lives set to {lives}.")

    @commands.hybrid_command(name="setnumber", description="Set the current number (admin)")
    @app_commands.describe(number="Set the next expected number")
    async def setnumber(self, ctx, number: int):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need Manage Guild permission.", ephemeral=True)
            return
        if number < 1:
            await ctx.send("Number must be >= 1.", ephemeral=True)
            return
        self._snapshot_guild(ctx.guild.id)
        data = self.data_manager.load_guild_data(ctx.guild.id)
        data["current_number"] = int(number)
        # Clear last user to avoid immediate double-count lock
        data["last_user_id"] = None

        # Theme deactivation (cosmetic-only): end Permafrost / Blackout if escalation phase drops.
        try:
            phase_now = self.get_escalation_phase(int(data.get("current_number", 1) or 1))
            if phase_now < 3:
                await self._end_permafrost_if_active(ctx.channel, ctx.channel.id, data)
            if phase_now < 4:
                await self._end_blackout_if_active(ctx.channel, ctx.channel.id, data)
        except Exception:
            pass

        self.data_manager.save_guild_data(ctx.guild.id, data)
        await ctx.send(f"✅ Current number set to {number}.")

    @commands.hybrid_command(name="addlife", description="Add lives (admin)")
    @app_commands.describe(count="How many lives to add (default 1)")
    async def addlife(self, ctx, count: int = 1):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need Manage Guild permission.", ephemeral=True)
            return
        self._snapshot_guild(ctx.guild.id)
        data = self.data_manager.load_guild_data(ctx.guild.id)
        data["lives"] = int(data.get("lives", 3)) + max(0, int(count))
        self.data_manager.save_guild_data(ctx.guild.id, data)
        await ctx.send(f"✅ Lives increased to {data['lives']}.")

    @commands.hybrid_command(name="takelife", description="Remove lives (admin)")
    @app_commands.describe(count="How many lives to remove (default 1)")
    async def takelife(self, ctx, count: int = 1):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need Manage Guild permission.", ephemeral=True)
            return
        self._snapshot_guild(ctx.guild.id)
        data = self.data_manager.load_guild_data(ctx.guild.id)
        data["lives"] = max(0, int(data.get("lives", 3)) - max(0, int(count)))
        self.data_manager.save_guild_data(ctx.guild.id, data)
        await ctx.send(f"✅ Lives decreased to {data['lives']}.")

    @commands.hybrid_command(name="setdedupwindow", description="Set announcement dedupe window seconds (admin)")
    async def setdedupwindow(self, ctx, seconds: float):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need Manage Guild permission.", ephemeral=True)
            return
        if seconds < 0:
            await ctx.send("Seconds must be >= 0.", ephemeral=True)
            return
        self.ANNOUNCE_DEDUP_WINDOW = float(seconds)
        await ctx.send(f"✅ Announcement dedupe window set to {seconds:.2f}s (runtime only).")

    @commands.hybrid_command(name="setreactioninterval", description="Set min reaction interval seconds (admin)")
    async def setreactioninterval(self, ctx, seconds: float):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need Manage Guild permission.", ephemeral=True)
            return
        if seconds < 0:
            await ctx.send("Seconds must be >= 0.", ephemeral=True)
            return
        self.REACTION_MIN_INTERVAL = float(seconds)
        await ctx.send(f"✅ Reaction min interval set to {seconds:.2f}s (runtime only).")

    @commands.hybrid_command(name="undo", description="Undo last admin change (if available)")
    async def undo(self, ctx):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need Manage Guild permission.", ephemeral=True)
            return
        ok = self._restore_snapshot(ctx.guild.id)
        if ok:
            await ctx.send("↩️ Restored previous state.")
        else:
            await ctx.send("❌ No snapshot available to restore.")

    @commands.hybrid_command(name="viewconfig", description="Show current counting configuration (admin)")
    async def viewconfig(self, ctx):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.send("❌ You need Manage Guild permission.", ephemeral=True)
            return
        data = self.data_manager.load_guild_data(ctx.guild.id)
        ch = data.get("channel_id")
        scope = data.get("difficulty_scope", "global")
        mode = data.get("difficulty_mode", "normal")
        embed = discord.Embed(title="⚙️ Counting Config", color=discord.Color.dark_teal())
        embed.add_field(name="Channel", value=(f"<#{ch}>" if ch else "Not set"), inline=True)
        embed.add_field(name="Current Number", value=str(data.get("current_number", 1)), inline=True)
        embed.add_field(name="Lives", value=str(data.get("lives", 3)), inline=True)
        embed.add_field(name="Scope", value=scope, inline=True)
        embed.add_field(name="Mode", value=mode, inline=True)
        embed.add_field(name="Dedupe Window", value=f"{self.ANNOUNCE_DEDUP_WINDOW:.2f}s", inline=True)
        embed.add_field(name="Reaction Interval", value=f"{self.REACTION_MIN_INTERVAL:.2f}s", inline=True)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.", ephemeral=True)

    @tasks.loop(minutes=5)
    async def save_data_task(self):
        """Periodically save guild configurations"""
        self.save_all_guild_configs()

        # Also run Murkoff/event expiry cleanup so cosmetic states don't get stuck
        # when nobody is counting for a while.
        try:
            for guild in list(getattr(self.bot, "guilds", []) or []):
                try:
                    await self._cleanup_murkoff_state_for_guild(guild)
                except Exception:
                    continue
        except Exception:
            pass

    @tasks.loop(hours=24)
    async def daily_reset_task(self):
        """Daily statistics reset"""
        # Could implement daily/weekly/monthly stat tracking here
        pass

    @save_data_task.before_loop
    async def before_save_data_task(self):
        await self.bot.wait_until_ready()

    @daily_reset_task.before_loop
    async def before_daily_reset_task(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(BringusCounting(bot))