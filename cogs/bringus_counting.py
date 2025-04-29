import discord
from discord.ext import commands
from discord import app_commands
import random
import aiohttp

class BringusCounting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.counting_channel_id = 1366535062765699103
        self.webhook_url = "https://discord.com/api/webhooks/1366526376647069857/HO3w2th_OWUrxAMS_dL14S9t_ClPuZyNnb4FtuZBAjpu_RT8_dXigFReeBzVyjGFlyoi"
        self.current_number = 1
        self.last_user_id = None
        self.lives = 3
        self.special_numbers = {
            42: ["The answer to Optical Media confusion."],
            69: ["Nice. Very optical. Very media."],
            404: ["Optical Media Not Found."],
            420: ["Optical Media permanently baked."]
        }

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.channel.id != self.counting_channel_id:
            return

        content = message.content.strip()
        if not content.isdigit():
            return

        number = int(content)
        if message.author.id == self.last_user_id:
            await message.channel.send(f"❌ You cannot count twice in a row! Lives Remaining: {self.lives}")
            return

        if number != self.current_number:
            self.lives -= 1
            if self.lives <= 0:
                await message.channel.send("⚠️ **Lives depleted!** Resetting count...")
                self.current_number = 1
                self.lives = 3
            else:
                await message.channel.send(f"❌ Wrong number! Lost a life. Lives Remaining: {self.lives}")
            return

        self.last_user_id = message.author.id
        self.current_number += 1

        if number in self.special_numbers:
            quote = random.choice(self.special_numbers[number])
            await self.send_webhook(quote)

    async def send_webhook(self, content):
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(self.webhook_url, session=session)
            await webhook.send(content=f"**Jon (Bringus) says:** "{content}"", username="Jon (Bringus)")

    @app_commands.command(name="lifes", description="Show current lives and number.")
    async def lifes(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🧮 Counting Progress", description=f"**Lives:** {self.lives}\n**Number:** {self.current_number}", color=0x1F1E33)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(BringusCounting(bot))