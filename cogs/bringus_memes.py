# Bringus Meme Commands Placeholder
from discord.ext import commands

class BringusMemes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def meme(self, ctx):
        await ctx.send('Random meme feature coming soon!')

async def setup(bot):
    await bot.add_cog(BringusMemes(bot))