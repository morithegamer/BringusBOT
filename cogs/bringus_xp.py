# XP System for Bringus Bot
from discord.ext import commands
import json

class BringusXP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        with open('database.json', 'r') as f:
            data = json.load(f)

        user_id = str(message.author.id)
        if user_id not in data.get('xp', {}):
            data.setdefault('xp', {})[user_id] = 0

        data['xp'][user_id] += 10

        with open('database.json', 'w') as f:
            json.dump(data, f, indent=4)

async def setup(bot):
    await bot.add_cog(BringusXP(bot))