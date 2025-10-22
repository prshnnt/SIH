from langgraph import Graph
from .nodes.input_node import create_input_node
from .nodes.memory_node import create_memory_node
from .nodes.llm_node import create_llm_node
from .nodes.formatting_node import create_format_node

# Create nodes
input_node = create_input_node()
memory_node = create_memory_node()
llm_node = create_llm_node()
format_node = create_format_node()

# Build graph
chat_graph = Graph("chat_graph")
chat_graph.add_nodes([input_node, memory_node, llm_node, format_node])
chat_graph.add_edges([
    (input_node, memory_node),
    (memory_node, llm_node),
    (llm_node, format_node)
])

# Run the graph as streaming async generator
async def run_chat_graph_stream(user_message: str):
    async for chunk in chat_graph.run({"user_input": user_message}, stream=True):
        yield chunk
