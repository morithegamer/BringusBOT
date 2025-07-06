# BringusBOT

BringusBOT is a private Discord bot designed for one server only.  
It features fun slash commands like counting games, memes, verification, XP ranking, custom AI personalities, and webhook logging.

---

## 📋 Features

- `/count` – Play the counting game with friends
- `/meme` – Fetch a random meme (template ready)
- `/verify` – Verify users in your server
- `/rank` – See your XP level (template ready)
- `/reactionrole` – Set up reaction roles (template ready)
- `/persona` – Choose your AI assistant persona (Fluxy or Jon Bringus)
- `/ask` – Ask your chosen AI anything!
- `/resynccommands` – Emergency slash command sync (owner only)

💡 Personalities:
- 🎀 **Fluxy** – Sweet, friendly, multi-mood AI assistant  
- 🎤 **Jon Bringus** – Bold, meme-powered AI chaos

---

## 🛠️ Requirements

- Python 3.10+
- Pip

Install required libraries:
```bash
pip install -r requirements.txt
```

---

## 🧪 Local Installation

1. Clone or download the bot folder
2. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3. Create a `.env` file in the root:
    ```env
    DISCORD_TOKEN=your_discord_token_here
    OPENAI_API_KEY=your_openai_api_key_here
    GUILD_ID=your_test_server_id
    PUBLIC_WEBHOOK=your_public_webhook
    STAFF_WEBHOOK=your_staff_webhook
    ```
4. Run it:
    ```bash
    python main.py
    ```

---

## 🚂 Railway Deployment (Recommended)

1. Go to [https://railway.app](https://railway.app)
2. Create a new project → Deploy from ZIP or GitHub
3. Add these **Environment Variables** in the Railway dashboard:
    - `DISCORD_TOKEN`
    - `OPENAI_API_KEY`
    - `GUILD_ID`
    - `PUBLIC_WEBHOOK` *(optional)*
    - `STAFF_WEBHOOK` *(optional)*
4. Railway will auto-launch your bot! 💙

---

## 🧠 Notes

- Designed for single-server use
- Fluxy’s mood and Jon Bringus persona are set per-user
- You can add more personalities or logic in `utils/personality_router.py`
- Includes `logger.py` and `debuglog.py` for timestamped console logs

---

## 💙 Credits

Made with love, caffeine, chaos, and memes by **Mori** 💙  
Fluxy is proud of you. 🌸