import aiohttp
import os
import base64

API_KEY = os.getenv("OPENAI_API_KEY")
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}
VISION_ENDPOINT = "https://api.openai.com/v1/chat/completions"

async def describe_image(image_bytes: bytes, mood: str = "funny"):
    """
    Analyzes an image and returns a description based on the mood.
    Supported moods: calm, funny, chaotic, dramatic
    """

    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    mood_prompts = {
        "calm": "You are a calm, factual assistant. Describe this image gently.",
        "funny": "You're a funny AI with meme energy. Describe this image humorously.",
        "chaotic": "You're unhinged and chaotic. Describe this image like a gremlin with attitude.",
        "dramatic": "You're poetic and mysterious. Describe this image like it belongs in a gothic novel."
    }

    system_prompt = mood_prompts.get(mood.lower(), mood_prompts["funny"])

    payload = {
        "model": "gpt-4-vision-preview",
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                    {"type": "text", "text": "What’s in this image?"}
                ]
            }
        ],
        "max_tokens": 500
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(VISION_ENDPOINT, headers=HEADERS, json=payload) as resp:
            if resp.status != 200:
                return f"[❌ Vision API Error {resp.status}]"
            result = await resp.json()
            return result["choices"][0]["message"]["content"].strip()
