import discord
from utils.fluxymode import is_fluxy_mode_enabled

from typing import Optional

def themed_embed(*, title: Optional[str] = None, description: Optional[str] = None) -> discord.Embed:
    if is_fluxy_mode_enabled():
        # 🌈 FLUXY MODE: Vibrant, glitch, chaos-coded aesthetic
        embed = discord.Embed(
            title=f"⚡ {title}" if title else None,
            description=description,
            color=discord.Color.from_rgb(255, 0, 255)  # Neon pink glitch
        )
        embed.set_footer(text="⚡ Fluxy Mode: ACTIVE | WebFlux Labs", icon_url=None)
    else:
        # Default vaporwave embed
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.from_rgb(137, 66, 245)  # Vapor purple
        )
        embed.set_footer(text="WebFlux Labs • Powered by Bringus + Fluxy 💙", icon_url=None)

    return embed
