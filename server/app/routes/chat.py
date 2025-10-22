from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from llm_backend.graph.chat_graph import run_chat_graph_stream
from pydantic import BaseModel

router = APIRouter()

class StreamChatRequest(BaseModel):
    chat_id: str
    message: str

@router.post("/send_stream")
async def send_message_stream(request: StreamChatRequest):
    async def event_generator():
        async for chunk in run_chat_graph_stream({
            "chat_id": request.chat_id,
            "user_message": request.message
        }):
            yield chunk
    return StreamingResponse(event_generator(), media_type="text/plain")
