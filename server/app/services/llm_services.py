from llm_backend.graph.chat_graph import run_chat_graph_stream, run_chat_graph_stream
import asyncio

async def process_chat(message: str) -> str:
    # Simple one-shot response (concatenate streamed output)
    chunks = []
    async for chunk in run_chat_graph_stream(message):
        chunks.append(chunk)
    return "".join(chunks)
