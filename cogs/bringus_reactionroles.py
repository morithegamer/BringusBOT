# Reaction Roles System
from discord.ext import commands
import discord

class BringusReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = discord.utils.get(guild.roles, name="ExampleRole")
        if role:
            member = guild.get_member(payload.user_id)
            if member:
                await member.add_roles(role)

async def setup(bot):
    await bot.add_cog(BringusReactionRoles(bot))