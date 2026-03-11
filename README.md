# 💙 BringusBOT

BringusBOT is a feature-packed Discord bot built around **slash commands**, hybrid moderation commands, and a few “always-on” systems (counting game, presence watcher, etc.).

This README documents the commands and config that exist in this repo (as of `BringusBOT-Final/main.py`).

---

## ✨ Features (high level)

### 🎰 Casino & Economy
- `/balance` – Check your casino coin balance
- `/daily` – Claim a daily bonus
- `/slot` – Slot machine (costs coins)
- `/coinflip` – Guess heads/tails to win/lose coins
- `/blackjack` – Blackjack vs the bot
- `/loot` – Random loot + optional 1-line AI flavor
- `/casinoevent` – AI-generated “casino event” announcement
- `/casino_leaderboard` – Top coin holders
- `/registerdealer` – Register as casino staff

### 🎭 Memes (Reddit)
- `/meme` – Fetch a meme (optionally by subreddit or category)
- `/nsfwmeme` – NSFW meme (NSFW channels only)
- `/memestats` – Meme stats
- `/memehelp` – Categories + usage

### 🤖 AI (Fluxy + Bringus)
Fluxy persona:
- `/ask` – Ask Fluxy (uses OpenAI)
- `/setfluxymood` – Set your Fluxy mood preset
- `/mystory` – Show what Fluxy remembers
- `/clearmemory` – Clear your Fluxy memory

Bringus (Jon):
- `/askbringus` – Talk to Bringus with a mood prompt

Utility AI commands:
- `/tarot` – Tarot reading
- `/summarize` – Summarize a text block
- `/remember` / `/recall` – Save/recall a fact
- `/captionimage` / `/visioncaption` – Caption an uploaded image

### 🔢 Counting Game
The counting game is message-driven (users post the next number). Admins can configure which channel it runs in and users can view stats.

Common commands:
- `/setcountchannel` – Set the counting channel
- `/countstats` – Stats + leaderboard
- `/lifes` – Show lives + progress
- `/achievements` – Counting achievements
- `/next` – Show the next expected number

### 🧰 Moderation & Utilities
This repo includes hybrid moderation commands (usable as prefix commands and/or slash commands depending on Discord.py support):
- `/kick`, `/ban`, `/timeout`, `/purge`, `/slowmode`, `/lock`, `/unlock`, warnings/cases, and more

### 🧠 Presence / Status / Diagnostics
- `/ownerstatus` – Shows what the configured owner/admin is doing
- `/botstats` – Bot stats
- `/setstatus` – Set bot status (admin)
- `/reload` – Reload a cog (admin)
- `/cmds` – Show command list
- `/version`, `/sysinfo`, `/performance`, `/ping`, `/uptime`

### 🐾 e621 (NSFW-only)
- `/e621` – Search e621 posts (NSFW channels only)
- `/e621help` – Search syntax help
- `/e621stats` – Your search statistics
- `/randomartist` – Random artist suggestion

### ☸️ Kubernetes (optional)
- `/kubectl` – Minimal kubectl-like helper (only enable this if you trust everyone who can run it)

---

## 📦 Setup

### Requirements
- Python 3.11+ (Docker uses 3.11)
- A Discord bot token
- (Optional) OpenAI API key for AI features

### Install
From the repo root:

```bash
cd BringusBOT-Final
pip install -r requirements.txt
```

### Environment (.env)
`BringusBOT-Final/main.py` reads configuration from environment variables.

Minimum required:
```env
DISCORD_TOKEN=your_bot_token
```

Common optional settings:
```env
OPENAI_API_KEY=your_openai_api_key

# If set, slash commands are additionally synced to this guild ID.
GUILD_ID=your_server_id

# Defaults
PREFIX=!
DEBUG=false
BOT_VERSION=v9.7.5

# Optional webhooks for startup / staff logging
PUBLIC_WEBHOOK=https://discord.com/api/webhooks/...
STAFF_WEBHOOK=https://discord.com/api/webhooks/...

# Reddit (required for meme commands)
REDDIT_CLIENT_ID=...
REDDIT_SECRET=...

# e621 (required for /e621)
E621_USERNAME=...
E621_API_KEY=...

# e621 extras
ENABLE_FLUXY_COMMENTS=1
MODLOG_CHANNEL_ID=123456789012345678
```

### Run locally
```bash
cd BringusBOT-Final
python main.py
```

### Run with Docker
```bash
cd BringusBOT-Final
docker compose up --build
```

---

## 💾 Data files
BringusBOT stores some state on disk:
- `casino_balances.json` – casino balances
- `data/counting_<guild_id>.json` – counting game data per guild
- `fluxy_data.db` – SQLite DB (user mood storage)
- `uptime_data.json` – restart/crash info
- `bringusbot.log` – log output

---

## 📄 License
MIT — see [../LICENSE](../LICENSE).

---

## 💙 Credits

Coded by **Mori** with 💙, 🍟, and memes.  
Powered by Discord.py, OpenAI, and a little chaos magic.  
Designed for one server only — **yours.**
