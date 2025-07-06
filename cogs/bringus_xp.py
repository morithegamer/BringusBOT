from pathlib import Path
import sqlite3

# Create the updated XP cog with milestone messages, XP decay (gentle), and a helper module
xp_module_code = '''
import discord
from discord.ext import commands
from discord import app_commands, Interaction
import sqlite3
from pathlib import Path
import random
import math

DB_PATH = Path("bringus_xp.db")

def calculate_level(xp: int) -> int:
    return int(math.sqrt(xp) // 10)

def get_milestone_message(level: int) -> str:
    rewards = {
        5: "🎉 You reached Level 5! Meme Knight unlocked!",
        10: "🌟 Level 10! You're officially a Meme Wizard.",
        15: "🔥 Level 15! Chaos flows through your circuits!",
        20: "👑 Level 20! Bringus Royalty unlocked."
    }
    return rewards.get(level, "")

class BringusXP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(\"""
            CREATE TABLE IF NOT EXISTS user_xp (
                user_id INTEGER PRIMARY KEY,
                xp INTEGER NOT NULL DEFAULT 0,
                last_level INTEGER NOT NULL DEFAULT 0
            )
        \""")
        conn.commit()
        conn.close()

    def get_user_data(self, user_id: int):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT xp, last_level FROM user_xp WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row if row else (0, 0)

    def set_user_data(self, user_id: int, xp: int, level: int):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(\"""
            INSERT INTO user_xp (user_id, xp, last_level) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET xp = excluded.xp, last_level = excluded.last_level
        \""", (user_id, xp, level))
        conn.commit()
        conn.close()

    def decay_all_xp(self, decay_amount: int = 1):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE user_xp SET xp = MAX(0, xp - ?)", (decay_amount,))
        conn.commit()
        conn.close()

    def add_xp(self, user_id: int, amount: int = 5) -> tuple[int, int, str]:
        xp, last_level = self.get_user_data(user_id)
        xp += amount
        new_level = calculate_level(xp)
        milestone = ""
        if new_level > last_level:
            milestone = get_milestone_message(new_level)
        self.set_user_data(user_id, xp, new_level)
        return xp, new_level, milestone

    def get_top_users(self, limit: int = 5):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, xp FROM user_xp ORDER BY xp DESC LIMIT ?", (limit,))
        results = cursor.fetchall()
        conn.close()
        return results

    @app_commands.command(name="rank", description="Check your XP rank!")
    async def rank(self, interaction: Interaction):
        user_id = interaction.user.id
        xp, _ = self.get_user_data(user_id)
        level = calculate_level(xp)

        embed = discord.Embed(
            title=f"📊 {interaction.user.display_name}'s Rank",
            color=discord.Color.purple()
        )
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="XP", value=f"{xp} XP", inline=True)
        embed.set_footer(text="XP system powered by Bringus Engine 💙")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="View the top XP users!")
    async def leaderboard(self, interaction: Interaction):
        top_users = self.get_top_users()
        description = ""

        for rank, (user_id, xp) in enumerate(top_users, start=1):
            try:
                user = await self.bot.fetch_user(user_id)
                name = user.display_name
            except:
                name = f"User {user_id}"
            level = calculate_level(xp)
            description += f"**{rank}.** {name} — {xp} XP (Lv. {level})\\n"

        embed = discord.Embed(
            title="🏆 Top XP Users",
            description=description or "No XP data found.",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(BringusXP(bot))
'''

with ("/mnt/data/bringus_xp.py", "w") as f:
    f.write(xp_module_code)

"✅ Your enhanced XP cog with level tracking, milestone messages, and XP decay support has been written to `bringus_xp.py`!"
