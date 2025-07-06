from discord.ext import commands

def is_admin():
    def predicate(ctx):
        return ctx.author.guild_permissions.administrator
    return commands.check(predicate)

def is_mod():
    def predicate(ctx):
        perms = ctx.author.guild_permissions
        return perms.manage_messages or perms.kick_members
    return commands.check(predicate)