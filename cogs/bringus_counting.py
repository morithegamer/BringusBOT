import discord
from discord.ext import commands
from discord import app_commands
import random
import aiohttp
import json

class BringusCounting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        with open('config.json', 'r') as f:
            config = json.load(f)
        self.counting_channel_id = config["counting_channel_id"]
        self.webhook_url = config["webhook_url"]
        self.lives = config["starting_lives"]
        self.current_number = 1
        self.last_user_id = None

        self.special_numbers = {
            42: ["The answer to Optical Media confusion."],
            69: ["Nice. Very optical. Very media.", "Achievement unlocked: Optical Disasters."],
            100: ["A century of Optical Mistakes!"],
            111: ["Triple Ones, triple trouble!"],
            123: ["Sequential failure achieved!"],
            200: ["Double Optical Errors."],
            222: ["Double triple Optical trouble."],
            300: ["THIS IS... OPTICAL MEDIA!"],
            301: ["Video still processing... Optical error ongoing."],
            321: ["Countdown to Optical Disaster."],
            333: ["Optical Media tripled."],
            404: ["Optical Media Not Found."],
            420: ["Optical Media permanently baked.", "Smoke rises, Media falls."],
            444: ["Cursed Optical Media activated."],
            500: ["Halfway to true disaster."],
            555: ["Triple confusion incoming."],
            666: ["Optical Media demons unleashed!"],
            777: ["Lucky Optical Perfection achieved!"],
            888: ["Infinite Optical Confusion loop."],
            911: ["Optical Emergency Reported!"],
            999: ["Almost Optical Apocalypse."],
            1000: ["Thousand media errors celebrated."],
            1959: ["Vintage Optical Glitch Detected."],
            1984: ["Optical Surveillance online... mistakes recorded."]
        }

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.channel.id != self.counting_channel_id:
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
                await message.channel.send("⚠️ **Lives depleted!** Resetting count...\n**Jon (Bringus) says:** \"You counted so wrong that Optical Media Bad gotten even worse!\"")
                self.current_number = 1
                self.lives = 1
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
            await webhook.send(content=f"**Jon (Bringus) says:** \"{content}\"", username="Jon (Bringus)")

    @app_commands.command(name="lifes", description="Show current lives and number.")
    async def lifes(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🧮 Velvet Room Counting Progress",
            description=f"**Lives Remaining:** {self.lives}\n**Current Number:** {self.current_number}",
            color=0x1F1E33
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(BringusCounting(bot))