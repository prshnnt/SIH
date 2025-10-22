from langgraph import Node

async def format_node_func(llm_stream):
    async for chunk in llm_stream:
        yield f"[Bot] {chunk}"

def create_format_node():
    return Node(
        "format_node",
        func=format_node_func,
        is_async=True,
        is_generator=True
    )
