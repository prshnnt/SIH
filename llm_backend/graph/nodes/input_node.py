from langgraph import Node

def create_input_node():
    return Node("user_input", func=lambda msg: {"user_message": msg})
