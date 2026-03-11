import discord
from discord.ext import commands
from discord import app_commands
import random
import json
import os
from datetime import datetime, timedelta, timezone
from openai import OpenAI

BALANCE_FILE = "casino_balances.json"

client = OpenAI()

# Ensure the balance file exists
if not os.path.exists(BALANCE_FILE):
    with open(BALANCE_FILE, "w") as f:
        json.dump({}, f)

def get_balances():
    with open(BALANCE_FILE, "r") as f:
        return json.load(f)

def save_balances(data):
    with open(BALANCE_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_balance(user_id):
    data = get_balances()
    return data.get(str(user_id), {}).get("balance", 1000)

def update_balance(user_id, amount):
    data = get_balances()
    user = data.get(str(user_id), {"balance": 1000, "last_daily": None})
    user["balance"] += amount
    data[str(user_id)] = user
    save_balances(data)

def set_daily(user_id):
    data = get_balances()
    user = data.get(str(user_id), {"balance": 1000, "last_daily": None})
    user["last_daily"] = datetime.utcnow().isoformat()
    data[str(user_id)] = user
    save_balances(data)

def can_claim_daily(user_id):
    data = get_balances()
    user = data.get(str(user_id), {"balance": 1000, "last_daily": None})
    if not user["last_daily"]:
        return True
    last_claim = datetime.fromisoformat(user["last_daily"])
    return datetime.utcnow() - last_claim >= timedelta(hours=24)

class Casino(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Check your casino coin balance.")
    async def balance(self, interaction: discord.Interaction):
        bal = get_balance(interaction.user.id)
        await interaction.response.send_message(f"\U0001F4B0 You have **{bal} coins**.", ephemeral=True)

    @app_commands.command(name="slot", description="Spin the slot machine!")
    async def slot(self, interaction: discord.Interaction):
        bal = get_balance(interaction.user.id)
        if bal < 100:
            await interaction.response.send_message("❌ Not enough coins! Spins cost 100.", ephemeral=True)
            return

        update_balance(interaction.user.id, -100)
        emojis = ["🍒", "🍋", "🍊", "🍉", "🔔", "⭐"]
        result = [random.choice(emojis) for _ in range(3)]
        win = len(set(result)) == 1
        msg = "🎉 Jackpot! +500 coins!" if win else "😢 Better luck next time."
        if win:
            update_balance(interaction.user.id, 500)
        await interaction.response.send_message(f"🎰 {' | '.join(result)}\n{msg}", ephemeral=True)

    @app_commands.command(name="daily", description="Claim your daily bonus!")
    async def daily(self, interaction: discord.Interaction):
        if not can_claim_daily(interaction.user.id):
            await interaction.response.send_message("🕒 You've already claimed your daily today!", ephemeral=True)
            return
        update_balance(interaction.user.id, 250)
        set_daily(interaction.user.id)
        await interaction.response.send_message("🎁 You claimed your **250 coin** daily bonus!", ephemeral=True)

    @app_commands.command(name="coinflip", description="Flip a coin to win or lose coins!")
    @app_commands.describe(guess="Heads or Tails")
    @app_commands.choices(guess=[
        app_commands.Choice(name="Heads", value="heads"),
        app_commands.Choice(name="Tails", value="tails")
    ])
    async def coinflip(self, interaction: discord.Interaction, guess: str):
        flip = random.choice(["heads", "tails"])
        win = (guess == flip)
        change = 150 if win else -100
        update_balance(interaction.user.id, change)
        result_msg = "🎉 You won 150 coins!" if win else "😢 You lost 100 coins."
        await interaction.response.send_message(f"🪙 The coin landed on **{flip.title()}**.\n{result_msg}", ephemeral=True)

    @app_commands.command(name="blackjack", description="Play a game of blackjack vs the bot!")
    async def blackjack(self, interaction: discord.Interaction):
        await interaction.response.defer()
        deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
        random.shuffle(deck)

        def draw(): return deck.pop()

        user_hand = [draw(), draw()]
        bot_hand = [draw(), draw()]

        def total(hand):
            t = sum(hand)
            aces = hand.count(11)
            while t > 21 and aces:
                t -= 10
                aces -= 1
            return t

        await interaction.response.send_message(
            f"🃏 Your hand: {user_hand} (Total: {total(user_hand)})\n🤖 Bot shows: [{bot_hand[0]}, ?]"
        )

        user_total = total(user_hand)
        bot_total = total(bot_hand)

        while user_total < 17:
            user_hand.append(draw())
            user_total = total(user_hand)

        while bot_total < 17:
            bot_hand.append(draw())
            bot_total = total(bot_hand)

        result = ""
        if user_total > 21:
            result = "😵 You busted! -200 coins."
            update_balance(interaction.user.id, -200)
        elif bot_total > 21 or user_total > bot_total:
            result = "🎉 You win! +300 coins."
            update_balance(interaction.user.id, 300)
        elif user_total < bot_total:
            result = "😔 You lost! -200 coins."
            update_balance(interaction.user.id, -200)
        else:
            result = "🤝 It's a tie! No coins lost."

        await interaction.followup.send(
            f"Final Hands:\n🧑 You: {user_hand} ({user_total})\n🤖 Bot: {bot_hand} ({bot_total})\n{result}"
        )

    @app_commands.command(name="casino_leaderboard", description="See who has the most coins!")
    async def casino_leaderboard(self, interaction: discord.Interaction):
        data = get_balances()
        sorted_data = sorted(data.items(), key=lambda x: x[1].get("balance", 0), reverse=True)[:10]
        embed = discord.Embed(title="🏆 Casino Leaderboard", color=discord.Color.gold())
        for i, (uid, info) in enumerate(sorted_data, 1):
            user = await self.bot.fetch_user(int(uid))
            embed.add_field(
                name=f"#{i} - {user.name}",
                value=f"💰 {info.get('balance', 0)} coins",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="loot", description="Try your luck at finding a random item or coin!")
    async def loot(self, interaction: discord.Interaction):
        outcomes = [
            ("✨ Rare Gem", 500),
            ("💵 Crumpled Bill", 100),
            ("🍀 Lucky Charm", 250),
            ("💣 Nothing but dust...", 0),
            ("🧱 Brick of nothing", 0)
        ]
        item, coins = random.choice(outcomes)
        update_balance(interaction.user.id, coins)

        try:
            lore = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You narrate loot rewards in a whimsical, fantasy casino setting."},
                    {"role": "user", "content": f"Write a 1-line reaction to finding {item}."}
                ]
            ).choices[0].message.content
        except Exception:
            lore = ""

        await interaction.response.send_message(
            f"🎁 You found: **{item}**\n💰 Coins gained: **{coins}**\n\n*{lore}*",
            ephemeral=True
        )

    @app_commands.command(name="casinoevent", description="Trigger a random casino event!")
    async def casino_event(self, interaction: discord.Interaction):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a creative casino announcer who generates exciting random events."},
                    {"role": "user", "content": "Generate a fun, unique casino event announcement with emoji flair."}
                ]
            )
            event_msg = response.choices[0].message.content
        except Exception as e:
            event_msg = f"⚠️ Failed to fetch AI event. Fallback event: 🎲 Everyone wins 50 coins! ({e})"
        await interaction.response.send_message(event_msg)

    @app_commands.command(name="registerdealer", description="Register as a Casino employee!")
    async def register_dealer(self, interaction: discord.Interaction):
        data = get_balances()
        uid = str(interaction.user.id)
        if "employee" in data.get(uid, {}):
            await interaction.response.send_message("👔 You're already registered as an employee!", ephemeral=True)
            return
        data.setdefault(uid, {"balance": 1000})
        data[uid]["employee"] = True
        save_balances(data)
        await interaction.response.send_message("🎲 Welcome to the Casino staff! You're now a dealer.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Casino(bot))

# This code defines a Casino cog for a Discord bot using discord.py and OpenAI's API.
# It allows users to check their balance, play games like slots and blackjack, claim daily bonuses,
# flip coins, view a leaderboard, find loot, trigger random casino events, and register as a dealer.
# The casino balance is stored in a JSON file, and the bot uses OpenAI to generate random casino events.
# The cog is designed to be loaded into a Discord bot using the `setup` function.