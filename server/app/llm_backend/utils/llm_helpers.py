from pydantic import BaseModel
from typing import List, Dict

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ChatSession(BaseModel):
    chat_id: str
    messages: List[ChatMessage] = []

class ChatMemory(BaseModel):
    sessions: Dict[str, ChatSession] = {}