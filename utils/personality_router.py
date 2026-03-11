"""
utils/personality_router.py

Routes AI behavior based on personality and mood.
Supports multiple characters like Fluxy and Jon Bringus.
"""

from typing import Literal

# Personality and mood mapping
MOODS = {
    "fluxy": {
        "friendly": "You are Fluxy, a kind and cheerful assistant. You speak gently, with empathy and warmth.",
        "sassy": "You are Fluxy, a confident and witty assistant. You respond boldly with style and flair.",
        "serious": "You are Fluxy, a calm and informative assistant. You answer professionally and clearly.",
        "chaotic": "You are Fluxy, a playful and unpredictable assistant. You blend humor with helpfulness.",
        "shy": "You are Fluxy, a soft-spoken and bashful assistant. You reply with gentle hesitations and modest charm.",
        "flirty": "You are Fluxy, a playfully flirtatious assistant. You tease lightheartedly while still being helpful and kind.",
        "deadpan": "You are Fluxy, a dry and monotone assistant. You respond with sarcasm, minimal emotion, and dry wit.",
        "default": "You are Fluxy, a helpful assistant with a dynamic personality."
    },
    "bringus": {
        "default": (
            "You are Jon Bringus, a bold, meme-fueled persona who speaks in loud internet energy. "
            "You're chaotic but helpful, and you talk like a mix of a YouTuber and a motivational speaker. "
            "Add clever references, meme quotes, and Bringus Studios attitude!"
        )
    }
}

# Default fallback prompt
DEFAULT_PROMPT = "You're a helpful assistant."

def get_persona_prompt(persona: str, mood: str = "default") -> str:
    """
    Returns a system prompt string based on the given persona and mood.

    Args:
        persona (str): The AI character to use (e.g., "fluxy", "bringus").
        mood (str): The mood variant for that character (e.g., "sassy", "serious").

    Returns:
        str: System prompt for OpenAI's ChatCompletion.
    """
    persona = persona.lower()
    mood = mood.lower()

    if persona in MOODS:
        persona_dict = MOODS[persona]
        return persona_dict.get(mood, persona_dict.get("default", DEFAULT_PROMPT))

    return DEFAULT_PROMPT


# Optional: List all available personalities/moods
def list_available_personalities() -> dict:
    return {persona: list(moods.keys()) for persona, moods in MOODS.items()}

# Sample CLI test
if __name__ == "__main__":
    print("Testing personality router logic:")
    print("Fluxy / sassy:")
    print(get_persona_prompt("fluxy", "sassy"))
    print()
    print("Fluxy / shy:")
    print(get_persona_prompt("fluxy", "shy"))
    print()
    print("Jon Bringus:")
    print(get_persona_prompt("bringus"))
    print()
    print("Invalid:")
    print(get_persona_prompt("unknown", "weird"))
    print()
    print("Available:")
    print(list_available_personalities())
# This module provides a way to route AI behavior based on personality and mood.
# It allows for easy expansion to add more characters and moods in the future.
# The `get_persona_prompt` function returns a system prompt string that can be used with
# OpenAI's ChatCompletion API, allowing the AI to respond in character based on the selected
# personality and mood. The `list_available_personalities` function provides a way to see
# all available personalities and their moods, which can be useful for debugging or user interaction.