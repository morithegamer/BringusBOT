import aiohttp
import base64
import os
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
import openai
from utils.helpers import safe_json_load, safe_json_dump, ensure_data_directory
ensure_data_directory()
from utils.fluxymode import is_fluxy_mode_enabled, set_fluxy_mode, toggle_fluxy_mode
from utils.theming import themed_embed
# Load environment variables

load_dotenv()

E621_USERNAME = os.getenv("E621_USERNAME")
E621_API_KEY = os.getenv("E621_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODLOG_CHANNEL_ID = int(os.getenv("MODLOG_CHANNEL_ID", 0))

HEADERS = {
    "User-Agent": f"FluxyBot/1.0 (by {E621_USERNAME} on e621)",
    "Authorization": "Basic " + base64.b64encode(f"{E621_USERNAME}:{E621_API_KEY}".encode()).decode()
}

openai.api_key = OPENAI_API_KEY

BANNED_TAGS = ["cub", "shota", "loli", "scat", "gore"]

async def fetch_e621_posts(query: str, limit: int = 5) -> Optional[Dict[str, Any]]:
    if not E621_USERNAME or not E621_API_KEY:
        print("Missing e621 credentials.")
        return None
    query = query.strip().replace(" ", "_").lower()
    if is_query_blocked(query):
        print(f"Query '{query}' is blocked.")
        return None

    url = f"https://e621.net/posts.json?tags={query}&limit={limit}&random=true"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    print(f"e621 API error: {resp.status}")
                    return None
                return await resp.json()
    except Exception as e:
        print(f"Exception fetching e621: {e}")
        return None

def is_query_blocked(query: str, banned: List[str] = BANNED_TAGS) -> bool:
    return any(tag in query.lower() for tag in banned)

def sanitize_query(query: str) -> str:
    return query.strip().replace(" ", "_").lower()

def summarize_tags(tags: Dict[str, List[str]], count: int = 5) -> str:
    general = tags.get("general", [])
    return ", ".join(general[:count]) if general else "No tags found."

def is_supported_image(url: Optional[str]) -> bool:
    if not url:
        return False
    return url.lower().endswith((".jpg", ".jpeg", ".png", ".gif"))

def format_embed(post: Dict[str, Any], query: str) -> Optional[dict]:
    file_url = post.get("file", {}).get("url")
    if not is_supported_image(file_url):
        return None

    embed = {
        "title": f"🔍 {query}",
        "url": f"https://e621.net/posts/{post['id']}",
        "description": f"💬 Tags: {summarize_tags(post['tags'])}\n👍 Score: {post['score']['total']} | 🅰️ Rating: `{post['rating']}`",
        "image_url": file_url
    }
    return embed

async def get_fluxy_comment(tags: List[str]) -> Optional[str]:
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You're a spicy, chaotic furry bot named Fluxy who reacts to e621 tags."},
                {"role": "user", "content": f"What do you think of these tags? {', '.join(tags[:10])}"}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI error: {e}")
        return None

async def send_modlog(bot, user, query: str):
    if not MODLOG_CHANNEL_ID:
        return
    log_channel = bot.get_channel(MODLOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"🔍 `{user}` searched e621: `{query}`")