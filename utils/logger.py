import aiohttp
import discord

class BringusLogger:
    def __init__(self, public_webhook: str, staff_webhook: str):
        self.public_webhook = public_webhook
        self.staff_webhook = staff_webhook

    async def send_simple_log(self, webhook_url: str, message: str, username: str = "Bringus Logger"):
        async with aiohttp.ClientSession() as session:
            payload = {
                "content": message,
                "username": username,
            }
            async with session.post(webhook_url, json=payload) as response:
                if response.status != 204:
                    print(f"Failed to send simple log: {response.status}")

    async def send_embed_log(self, webhook_url: str, title: str, description: str, color: int = 0x3498db):
        embed = discord.Embed(title=title, description=description, color=color)
        async with aiohttp.ClientSession() as session:
            payload = {
                "embeds": [embed.to_dict()],
                "username": "Bringus Logger"
            }
            async with session.post(webhook_url, json=payload) as response:
                if response.status != 204:
                    print(f"Failed to send embed log: {response.status}")

    async def public_log(self, message: str):
        await self.send_simple_log(self.public_webhook, message)

    async def staff_log(self, message: str):
        await self.send_simple_log(self.staff_webhook, message)

    async def public_embed(self, title: str, description: str):
        await self.send_embed_log(self.public_webhook, title, description)

    async def staff_embed(self, title: str, description: str):
        await self.send_embed_log(self.staff_webhook, title, description)