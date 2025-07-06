import discord

def create_embed(title: str, description: str, color=discord.Color.blurple()):
    return discord.Embed(title=title, description=description, color=color)