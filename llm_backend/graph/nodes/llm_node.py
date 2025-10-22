from langgraph import Node
import openai
import os
from utils.llm_helpers import ChatSession

openai.api_key = os.getenv("OPENAI_API_KEY")

async def llm_node_func(inputs: dict):
    session: ChatSession = inputs["chat_context"]
    messages = [{"role": msg.role, "content": msg.content} for msg in session.messages]

    # Stream response
    response = await openai.ChatCompletion.acreate(
        model="gpt-3.5-turbo",
        messages=messages,
        stream=True
    )

    collected = ""
    async for event in response:
        if "choices" in event and len(event["choices"]) > 0:
            delta = event["choices"][0]["delta"].get("content")
            if delta:
                collected += delta
                yield delta  # Stream partial content

    # Save assistant message
    session.messages.append({"role": "assistant", "content": collected})

def create_llm_node():
    return Node(
        "llm_node",
        func=llm_node_func,
        is_async=True,
        is_generator=True
    )
