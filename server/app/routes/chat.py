from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.llm_backend.graph.chat_graph import chat_with_database
from pydantic import BaseModel

router = APIRouter()

class StreamChatRequest(BaseModel):
    chat_id: str
    message: str

@router.post("/send_stream")
def send_message_stream(request: StreamChatRequest):
    return chat_with_database(request.message)
