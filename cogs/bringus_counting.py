import discord
from discord.ext import commands
from discord import app_commands
import random
import aiohttp
from collections import defaultdict
import datetime

class BringusCounting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.counting_channel_id = 1366535062765699103
        self.webhook_url = "https://discord.com/api/webhooks/1390609885518888960/71kdy00X8Urt-Xhua99VHpfFj1PVwMABAPhIlLX9TLmCDooSaVRK0zWDl9poe8L-7nU4"
        self.current_number = 1
        self.last_user_id = None
        self.lives = 3

        self.count_stats = defaultdict(int)
        self.failures = 0
        self.last_fail_user = None
        self.last_reset = datetime.datetime.now(datetime.timezone.utc)
        self.streaks = defaultdict(int)
        self.highest_streak = 0
        self.highest_streak_user = None
        self.bringushell_mode = False

        self.special_numbers = {
            42: ["The answer to Optical Media confusion."],
            69: ["Nice. Very optical. Very media.", "Achievement unlocked: Optical Disasters."],
            100: ["A century of Optical Mistakes!"],
            111: ["Triple Ones, triple trouble!"],
            123: ["Sequential failure achieved!"],
            200: ["Double Optical Errors."],
            222: ["Double triple Optical trouble."],
            256: ["Byte-sized Optical Glitch."],
            300: ["THIS IS... OPTICAL MEDIA!"],
            301: ["Video still processing... Optical error ongoing."],
            314: ["Pi Optical Chaos initiated."],
            321: ["Countdown to Optical Disaster."],
            333: ["Optical Media tripled."],
            404: ["Optical Media Not Found."],
            418: ["I'm a teapot full of Optical Media."],
            420: ["Optical Media permanently baked.", "Smoke rises, Media falls."],
            444: ["Cursed Optical Media activated."],
            500: ["Halfway to true disaster."],
            555: ["Triple confusion incoming."],
            666: ["Optical Media demons unleashed!"],
            694: ["One short of Nice overload."],
            696: ["Double trouble with Optical Naughtiness."],
            700: ["Lucky Seven... error in progress."],
            707: ["Agent 707 reporting for Optical duty."],
            720: ["Optical spin detected: 720 degrees of chaos."],
            727: ["Flight 727: Destination Optical Doom."],
            741: ["Optical Voltage Overload."],
            747: ["High-flying Optical Glitch inbound!"],
            777: ["Lucky Optical Perfection achieved!"],
            800: ["Eight hundred glitches and counting."],
            808: ["Optical beats dropping — system error thump."],
            818: ["Area Code: Optical Trouble."],
            848: ["Optical Symmetry: Glitch in stereo."],
            888: ["Infinite Optical Confusion loop."],
            900: ["Approaching catastrophic levels..."],
            911: ["Optical Emergency Reported!"],
            999: ["Almost Optical Apocalypse."],
            1000: ["Thousand media errors celebrated."],
            1337: ["Leet Optical Hack detected."],
            1729: ["Hardy Optical Paradox activated."],
            1959: ["Vintage Optical Glitch Detected."],
            1984: ["Optical Surveillance online... mistakes recorded."],
            2000: ["Y2K: Optical collapse narrowly avoided."],
            2025: ["Optical AI Error: Current year misaligned."],
            2049: ["Blade Runner Mode: Optical Replicant Malfunction."],
            2077: ["CyberGlitch initiated. Optical chaos eternal."],
            2525: ["If counting is still alive... Optical Dystopia begins."],
            3030: ["Deltron Optical Future engaged!"],
            5050: ["Perfectly balanced as all errors should be."],
            6666: ["Quadruple Optical Doom. RIP counting."],
            7777: ["Optical Jackpot. You win... or do you?"],
            9001: ["It's over 9000! Optical Media shattered."],
            -1: [
                "You counted so wrong, even Jon can't believe it...",
                "Optical spirits are weeping.",
                "The count just got cursed. Good job.",
                "BRINGUS. IS. DISAPPOINTED."
            ]
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
            await message.add_reaction("💀")
            return

        expected_number = self.current_number
        if self.bringushell_mode:
            expected_number = random.randint(self.current_number - 2, self.current_number + 2)

        if number != expected_number:
            self.lives -= 1
            self.failures += 1
            self.last_fail_user = message.author
            self.streaks[message.author.id] = 0
            await message.add_reaction("💀")
            if self.lives <= 0:
                fail_quote = random.choice(self.special_numbers[-1])
                await message.channel.send(
                    f"⚠️ **Lives depleted!** Resetting count...\n\n**Jon (Bringus) says:** \"{fail_quote}\""
                )
                self.current_number = 1
                self.lives = 3
                self.last_reset = datetime.datetime.utcnow()
            else:
                await message.channel.send(f"❌ Wrong number! Lost a life. Lives Remaining: {self.lives}")
            return

        self.last_user_id = message.author.id
        self.current_number += 1
        self.count_stats[message.author.id] += 1
        self.streaks[message.author.id] += 1
        if self.streaks[message.author.id] > self.highest_streak:
            self.highest_streak = self.streaks[message.author.id]
            self.highest_streak_user = message.author
        await message.add_reaction("✅")

        if number in self.special_numbers:
            quote = random.choice(self.special_numbers[number])
            await self.send_webhook(quote)

    async def send_webhook(self, content):
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(self.webhook_url, session=session)
            await webhook.send(content=f"**Jon (Bringus) says:** \"{content}\"", username="Jon (Bringus)")

    @app_commands.command(name="lifes", description="Show current lives and current number in counting game.")
    async def lifes(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🧮 Velvet Room Counting Progress",
            description=f"**Lives Remaining:** {self.lives}\n**Current Number:** {self.current_number}",
            color=0x1F1E33
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="countstats", description="Show top counters and stats.")
    async def countstats(self, interaction: discord.Interaction):
        top_counters = sorted(self.count_stats.items(), key=lambda x: x[1], reverse=True)[:5]
        description = "\n".join(
            [f"<@{user_id}> — {count} counts" for user_id, count in top_counters]
        ) or "No stats yet."
        embed = discord.Embed(title="🏆 Top Counters", description=description, color=0xFFD700)
        embed.set_footer(text=f"Total Failures: {self.failures} | Last Reset: {self.last_reset.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        if self.last_fail_user:
            embed.add_field(name="Last Fail", value=f"<@{self.last_fail_user.id}>", inline=False)
        if self.highest_streak_user:
            embed.add_field(name="🔥 Highest Streak", value=f"<@{self.highest_streak_user.id}> — {self.highest_streak} counts", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bringushell", description="Toggle BringusHell Mode: Randomizes the expected number!")
    async def bringushell(self, interaction: discord.Interaction):
        self.bringushell_mode = not self.bringushell_mode
        state = "ON 🔥" if self.bringushell_mode else "OFF 🧊"
        await interaction.response.send_message(f"BringusHell Mode is now **{state}**!")

async def setup(bot: commands.Bot):
    await bot.add_cog(BringusCounting(bot))
