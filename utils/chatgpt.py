from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
import os
from typing import List

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def ask_chatgpt(prompt: str, system_prompt: str = "") -> str:
    try:
        typed_messages: List[ChatCompletionMessageParam] = []
        if system_prompt:
            sys_msg: ChatCompletionSystemMessageParam = {"role": "system", "content": system_prompt}
            typed_messages.append(sys_msg)
        user_msg: ChatCompletionUserMessageParam = {"role": "user", "content": prompt}
        typed_messages.append(user_msg)

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=typed_messages,
        )
        content = response.choices[0].message.content
        return content.strip() if content else ""
    except Exception as e:
        return f"⚠️ Fluxy encountered an error: {e}"
