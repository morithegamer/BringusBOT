def build_gpt_prompt(role: str, user_input: str, username: str = "User"):
    if role == "fluxy":
        return [
            {"role": "system", "content": "You are Fluxy, a helpful, intelligent, and caring female assistant."},
            {"role": "user", "content": user_input}
        ]
    elif role == "tarot":
        return [
            {"role": "system", "content": "You are a professional tarot reader. Draw a tarot card and give a mystical, symbolic interpretation."},
            {"role": "user", "content": f"Draw a tarot card for {username}."}
        ]
    elif role == "meme_tarot":
        return [
            {"role": "system", "content": "You are Bringus the Seer, a chaotic tarot reader. Draw a meme or cursed tarot card and give a dramatic fortune."},
            {"role": "user", "content": f"Give a meme tarot reading for {username}."}
        ]
    else:
        return [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": user_input}
        ]