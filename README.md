# BringusBOT

BringusBOT is a private Discord bot designed for one server only.
It features fun slash commands like counting games, memes, verification, XP ranking, and a public/staff logging system via webhooks.

---

## 📋 Features
- `/count` - Play the counting game with friends!
- `/meme` - Fetch a random meme (template ready)
- `/verify` - Verify users in your server
- `/rank` - See your XP level (template ready)
- `/reactionrole` - Set up reaction roles (template ready)
- Public Webhook Logger
- Staff Webhook Logger
- Server-private slash command sync (your server only)

---

## 🛠️ Requirements
- Python 3.10+
- Pip
- `discord.py`
- `aiohttp`

Install required libraries:
```bash
pip install -r requirements.txt
```

---

## 🚀 Installation
1. Clone or download the bot folder.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `config.json` file (already provided) and fill in:
   - Your bot token
   - Public webhook URL
   - Staff webhook URL

Example `config.json`:
```json
{
  "token": "YOUR_DISCORD_BOT_TOKEN",
  "prefix": "!",
  "public_webhook": "https://discord.com/api/webhooks/your-public-webhook-here",
  "staff_webhook": "https://discord.com/api/webhooks/your-staff-webhook-here"
}
```

4. Run Bringus:
```bash
python main.py
```

---

## ⚡ Running BringusBOT
- The bot will automatically sync all slash commands **ONLY** to your server.
- You will see slash commands like `/count`, `/meme`, `/verify` appear after sync.
- Webhook logs will post actions/events into your public and staff channels.

---

## 🔧 Notes
- Bringus is coded to sync slash commands to **only your server** using your provided server ID.
- This keeps the bot private and avoids accidental global command registration.

---

## ❤️ Credits
Built with patience, hard work, and lots of 💙 by the owner of BringusBOT.

Special thanks to ChatGPT for helping rebuild it cleanly!
