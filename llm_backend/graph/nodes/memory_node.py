from langgraph import Node
from utils.llm_helpers import ChatMemory, ChatMessage

# Global memory
conversation_memory = ChatMemory()

async def memory_node_func(inputs: dict):
    user_message = inputs["user_message"]
    chat_id = inputs.get("chat_id", "default")  # fallback chat_id

    # Create session if not exists
    if chat_id not in conversation_memory.sessions:
        conversation_memory.sessions[chat_id] = ChatSession(chat_id=chat_id)

    # Add user message
    conversation_memory.sessions[chat_id].messages.append(ChatMessage(role="user", content=user_message))

    # Return session context
    return {"chat_context": conversation_memory.sessions[chat_id]}

def create_memory_node():
    return Node(
        "memory_node",
        func=memory_node_func,
        is_async=True
    )
