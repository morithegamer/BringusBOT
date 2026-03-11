import discord
from typing import Optional

def create_embed(
    title: str,
    description: str,
    color: discord.Color = discord.Color.blurple(),
    footer: Optional[str] = None,
    thumbnail: Optional[str] = None,
    image: Optional[str] = None,
    timestamp: Optional[bool] = False
) -> discord.Embed:
    """
    Creates a reusable Discord embed with optional styling.

    Args:
        title (str): Embed title.
        description (str): Main content body.
        color (discord.Color): Embed border color. Default is blurple.
        footer (str, optional): Footer text.
        thumbnail (str, optional): URL to a thumbnail image.
        image (str, optional): URL to a larger image.
        timestamp (bool, optional): If True, adds current timestamp.

    Returns:
        discord.Embed: Configured embed object.
    """
    embed = discord.Embed(title=title, description=description, color=color)

    if footer:
        embed.set_footer(text=footer)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    if timestamp:
        embed.timestamp = discord.utils.utcnow()

    return embed
