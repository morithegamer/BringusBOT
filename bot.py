import discord
from discord.ext import commands
import os
import pingjar

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    pingjar.init_db()
    total = pingjar.get_total_debt()
    await bot.change_presence(activity=discord.Game(name=f"Ping Jar - ${total} collected 💸"))
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.mentions:
        pingjar.add_ping_fine(message.author.id)
        balance = pingjar.get_user_balance(message.author.id)
        total = pingjar.get_total_debt()

        try:
            await message.author.send(
                f"📣 That ping was unnecessary!\n💸 +$1 added to your Ping Jar.\nCurrent balance: ${balance}"
            )
        except discord.Forbidden:
            print(f"Couldn't DM {message.author} — DMs may be off.")

        # 🔁 Update status with latest total
        await bot.change_presence(activity=discord.Game(name=f"Ping Jar - ${total} collected 💸"))

    await bot.process_commands(message)

@bot.command(name="pingjar")
async def pingjar_balance(ctx):
    balance = pingjar.get_user_balance(ctx.author.id)
    await ctx.send(f"💼 {ctx.author.mention}, your Ping Jar balance is: **${balance}** 💸")

bot.run(os.getenv("DISCORD_TOKEN"))
