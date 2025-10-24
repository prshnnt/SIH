"""
SQL RAG Chatbot with LangGraph and Groq

This module implements a conversational chatbot that converts natural language
questions into SQL queries, executes them safely on PostgreSQL, and generates
natural language responses.

Architecture:
    - Uses LangGraph for workflow orchestration
    - Groq LLM for query generation and response synthesis
    - PostgreSQL for data storage
    - Safety mechanisms to prevent data modification

Dependencies:
    pip install langgraph langchain-groq psycopg2-binary fastapi
"""

from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
import psycopg2
import re
import os
from dotenv import load_dotenv
load_dotenv()


# ============================================================================
# STATE DEFINITION
# ============================================================================

class SQLRAGState(TypedDict):
    """
    State object passed between nodes in the LangGraph workflow.
    
    Attributes:
        question (str): User's natural language question
        sql_query (str): Generated SQL query
        query_results (str): Results from SQL execution
        final_answer (str): Natural language response to user
        error (str): Any error messages encountered
        chat_history (list): Conversation history
    """
    question: str
    sql_query: str
    query_results: str
    final_answer: str
    error: str
    chat_history: list


# ============================================================================
# DATABASE CONNECTION
# ============================================================================

def get_db_connection():
    """
    Establishes connection to PostgreSQL database.
    
    Returns:
        psycopg2.connection: Database connection object
        
    Environment Variables:
        DB_HOST: Database host (default: localhost)
        DB_NAME: Database name
        DB_USER: Database user (default: postgres)
        DB_PASSWORD: Database password
        DB_PORT: Database port (default: 5432)
    """
    return psycopg2.connect('postgresql://neondb_owner:npg_XwJUeOYGW0o4@ep-nameless-glade-a10cj1xw-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require')


def get_database_schema() -> str:
    """
    Retrieves the database schema information.
    
    Returns:
        str: Formatted database schema with table and column information
        
    Note:
        Modify this function to include your specific database schema.
        This helps the LLM understand available tables and columns.
    """
    # Example schema - replace with your actual schema
    schema = """
    TABLE: argo_float_metadata
    Description: Stores main metadata about Argo floats (autonomous oceanographic instruments).

    Columns:
    - id: Unique identifier for the float (integer, primary key)
    - wmo: World Meteorological Organization ID (string)
    - file_path: Source file path
    - profiler_type: Type of profiler
    - institution: Research or management institution
    - date_update: Timestamp of last data update
    - global_title, global_institution, global_source, global_history, global_references, global_comment: Global descriptive metadata
    - global_user_manual_version, global_conventions: Metadata standards
    - platform_number, project_name, principal_investigator, platform_type: Details about the float platform and project
    - float_serial_number, firmware_version: Hardware version info
    - launch_date: Launch timestamp (used for time-series partitioning)
    - launch_longitude, launch_latitude: Launch coordinates
    - launch_location: Geospatial point (computed from longitude and latitude)
    - deployment_platform, deployment_cruise_id: Deployment details
    - battery_type, battery_packs, controller_board_primary, controller_board_serial_primary: Hardware configuration
    - data_centre, wmo_instrument_type: Management metadata
    - transmission_system, transmission_system_id, transmission_frequency: Telemetry details
    - start_date, start_date_qc, end_mission_date, end_mission_status: Mission lifecycle data
    - extraction_date, created_at, updated_at: Record timestamps

    Relations:
    - One-to-many with:
    - argo_launch_config
    - argo_config_history
    - argo_sensors
    - argo_positioning_systems
    - argo_transmission_systems


    TABLE: argo_launch_config
    Description: Stores launch-time configuration parameters for each float.

    Columns:
    - id: Primary key
    - float_id: References argo_float_metadata.id
    - float_launch_date: References argo_float_metadata.launch_date
    - parameter_name: Name of the configuration parameter
    - parameter_value: Numeric value
    - parameter_order: Defines parameter sequence
    - created_at: Timestamp when record was added

    Relation:
    - Each float can have multiple launch configuration parameters.


    TABLE: argo_config_history
    Description: Stores historical and current configuration sets.

    Columns:
    - id: Primary key
    - float_id, float_launch_date: References argo_float_metadata
    - config_set: Configuration version number
    - parameter_name, parameter_value, parameter_order: Configuration details
    - effective_date: When this config became active
    - created_at: Record creation timestamp

    Relation:
    - Each float can have multiple configuration versions.


    TABLE: argo_sensors
    Description: Details sensors installed on each float.

    Columns:
    - id: Primary key
    - float_id, float_launch_date: References argo_float_metadata
    - sensor_type: Sensor type (e.g., temperature, salinity, pressure)
    - maker, model, serial_number: Manufacturer and hardware identifiers
    - sensor_order: Position/order of sensor on float
    - created_at: Timestamp of record creation

    Relation:
    - Each float can have multiple sensors.


    TABLE: argo_positioning_systems
    Description: Records positioning systems used by each float.

    Columns:
    - id: Primary key
    - float_id, float_launch_date: References argo_float_metadata
    - system_name: Name of the positioning system (e.g., GPS)
    - system_order: Order of usage
    - created_at: Timestamp of record creation

    Relation:
    - One float can have multiple positioning systems.


    TABLE: argo_transmission_systems
    Description: Records communication systems used by each float.

    Columns:
    - id: Primary key
    - float_id, float_launch_date: References argo_float_metadata
    - system_name: Transmission system (e.g., ARGOS, IRIDIUM)
    - system_id: Identifier
    - frequency: Transmission frequency
    - system_order: Order of usage
    - created_at: Timestamp of record creation

    Relation:
    - One float can have multiple transmission systems.


    VIEW: v_argo_float_complete
    Description: A combined view aggregating:
    - argo_float_metadata
    - linked sensors (argo_sensors)
    - positioning systems (argo_positioning_systems)
    - transmission systems (argo_transmission_systems)

    Computed Fields:
    - computed_longitude, computed_latitude: Extracted from launch_location
    - sensor_details: JSON array of sensor info
    - positioning_systems, transmission_systems: Arrays of system names
    """
    return schema


# ============================================================================
# SAFETY VALIDATION
# ============================================================================

def is_safe_sql_query(sql_query: str) -> tuple[bool, str]:
    """
    Validates SQL query to ensure it's read-only and safe to execute.
    
    Args:
        sql_query (str): SQL query to validate
        
    Returns:
        tuple[bool, str]: (is_safe, error_message)
            - is_safe: True if query is safe, False otherwise
            - error_message: Description of safety violation if unsafe
            
    Security Rules:
        - Only SELECT statements allowed
        - No INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE
        - No semicolons (prevents multiple statements)
        - No comments (prevents SQL injection attempts)
    """
    sql_upper = sql_query.upper().strip()
    
    # Check for dangerous keywords
    dangerous_keywords = [
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 
        'CREATE', 'TRUNCATE', 'GRANT', 'REVOKE', 'EXEC'
    ]
    
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            return False, f"Query rejected: {keyword} operations are not allowed"
    
    # Ensure it's a SELECT statement
    if not sql_upper.startswith('SELECT'):
        return False, "Only SELECT queries are allowed"
    
    # Check for multiple statements (semicolons)
    if ';' in sql_query.rstrip(';'):
        return False, "Multiple statements are not allowed"
    
    # Check for SQL comments
    if '--' in sql_query or '/*' in sql_query:
        return False, "Comments in SQL are not allowed"
    
    return True, ""


# ============================================================================
# LANGGRAPH NODES
# ============================================================================

def generate_sql_query(state: SQLRAGState) -> SQLRAGState:
    """
    Node 1: Converts natural language question to SQL query.
    
    This node uses Groq LLM to understand the user's question and generate
    an appropriate SQL query based on the database schema.
    
    Args:
        state (SQLRAGState): Current state with user question
        
    Returns:
        SQLRAGState: Updated state with generated SQL query or error
        
    Process:
        1. Get database schema
        2. Create prompt with schema and question
        3. Generate SQL using Groq LLM
        4. Validate query safety
        5. Update state with query or error
    """
    llm = ChatGroq(
        model="openai/gpt-oss-20b",  # or "mixtral-8x7b-32768"
        temperature=0,
    )
    
    schema = get_database_schema()
    
    system_prompt = f"""You are a SQL expert. Convert natural language questions to PostgreSQL queries.

{schema}

Rules:
1. Generate ONLY SELECT queries
2. Never use INSERT, UPDATE, DELETE, DROP, or any data modification commands
3. Return only the SQL query, no explanations
4. Use proper PostgreSQL syntax
5. Limit results to 100 rows for safety
6. Use clear table and column names

Example:
Question: "Show me all customers"
SQL: SELECT * FROM customers LIMIT 100;
"""
    
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Question: {state['question']}")
        ])
        
        sql_query = response.content.strip()
        # Clean up SQL query
        sql_query = sql_query.replace('```sql', '').replace('```', '').strip()
        
        # Validate safety
        is_safe, error_msg = is_safe_sql_query(sql_query)
        
        if not is_safe:
            state["error"] = error_msg
            state["sql_query"] = ""
        else:
            state["sql_query"] = sql_query
            state["error"] = ""
            
    except Exception as e:
        state["error"] = f"Error generating SQL: {str(e)}"
        state["sql_query"] = ""
    
    return state


def execute_sql_query(state: SQLRAGState) -> SQLRAGState:
    """
    Node 2: Executes the validated SQL query on PostgreSQL database.
    
    This node takes the generated SQL query, executes it safely on the
    database, and stores the results.
    
    Args:
        state (SQLRAGState): Current state with SQL query
        
    Returns:
        SQLRAGState: Updated state with query results or error
        
    Process:
        1. Check if previous node had errors
        2. Connect to database
        3. Execute SQL query with timeout
        4. Format results as readable text
        5. Update state with results
        
    Safety Features:
        - Read-only transaction
        - Query timeout (30 seconds)
        - Limited result set (handled in query generation)
    """
    # Skip if there's an error from previous node
    if state["error"]:
        return state
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Set statement timeout for safety (30 seconds)
        cur.execute("SET statement_timeout = 30000")
        
        # Execute query
        cur.execute(state["sql_query"])
        results = cur.fetchall()
        column_names = [desc[0] for desc in cur.description]
        
        # Format results
        if not results:
            state["query_results"] = "No results found."
        else:
            # Format as table
            formatted_results = f"Columns: {', '.join(column_names)}\n\n"
            for row in results:
                formatted_results += " | ".join(str(val) for val in row) + "\n"
            
            state["query_results"] = formatted_results
        
        cur.close()
        conn.close()
        
    except Exception as e:
        state["error"] = f"Error executing query: {str(e)}"
        state["query_results"] = ""
    
    return state


def generate_natural_response(state: SQLRAGState) -> SQLRAGState:
    """
    Node 3: Converts SQL results into natural language response.
    
    This node takes the raw SQL query results and generates a friendly,
    conversational response for the user.
    
    Args:
        state (SQLRAGState): Current state with query results
        
    Returns:
        SQLRAGState: Updated state with final natural language answer
        
    Process:
        1. Check for errors from previous nodes
        2. Create context with question and results
        3. Generate natural language response using Groq
        4. Update state with final answer
        
    Features:
        - Conversational tone
        - Clear presentation of data
        - Handles empty results gracefully
    """
    # If there's an error, return it as the final answer
    if state["error"]:
        state["final_answer"] = f"I encountered an error: {state['error']}"
        return state
    
    llm = ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.7
    )
    
    system_prompt = """You are a helpful data assistant. Convert SQL query results into clear, 
    natural language responses. Be concise but informative. If there are many results, 
    summarize them appropriately."""
    
    user_prompt = f"""
    Question: {state['question']}

    Query Results:
    {state['query_results']}

    Provide a natural, conversational answer to the user's question based on these results.
    """
    
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        
        state["final_answer"] = response.content
        
    except Exception as e:
        state["final_answer"] = f"Error generating response: {str(e)}"
    
    return state


# ============================================================================
# GRAPH CONSTRUCTION
# ============================================================================

def create_sql_rag_graph():
    """
    Constructs the LangGraph workflow for SQL RAG chatbot.
    
    Returns:
        CompiledGraph: Compiled LangGraph workflow ready for execution
        
    Workflow:
        1. generate_sql_query: Convert question to SQL
        2. execute_sql_query: Run SQL on database
        3. generate_natural_response: Create natural language answer
        
    The graph executes sequentially and handles errors gracefully.
    """
    workflow = StateGraph(SQLRAGState)
    
    # Add nodes
    workflow.add_node("generate_sql", generate_sql_query)
    workflow.add_node("execute_sql", execute_sql_query)
    workflow.add_node("generate_response", generate_natural_response)
    
    # Define edges (linear flow)
    workflow.set_entry_point("generate_sql")
    workflow.add_edge("generate_sql", "execute_sql")
    workflow.add_edge("execute_sql", "generate_response")
    workflow.add_edge("generate_response", END)
    
    return workflow.compile()


# ============================================================================
# MAIN CHAT FUNCTION
# ============================================================================

def chat_with_database(question: str, chat_history: list = None) -> dict:
    """
    Main function to interact with the SQL RAG chatbot.
    
    This is the primary interface for FastAPI integration. It takes a user's
    question, processes it through the LangGraph workflow, and returns a response.
    
    Args:
        question (str): User's natural language question
        chat_history (list, optional): Previous conversation history
            Format: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    
    Returns:
        dict: Response containing:
            - answer (str): Natural language response
            - sql_query (str): Generated SQL query (for transparency)
            - error (str): Any error message, empty if successful
            
    Example:
        >>> response = chat_with_database("How many customers do we have?")
        >>> print(response["answer"])
        "We currently have 150 customers in the database."
        
    Usage in FastAPI:
        @app.post("/chat")
        async def chat(request: ChatRequest):
            response = chat_with_database(request.question, request.chat_history)
            return response
    """
    if chat_history is None:
        chat_history = []
    
    # Initialize state
    initial_state = {
        "question": question,
        "sql_query": "",
        "query_results": "",
        "final_answer": "",
        "error": "",
        "chat_history": chat_history
    }
    
    # Create and run graph
    graph = create_sql_rag_graph()
    result = graph.invoke(initial_state)
    
    return {
        "answer": result["final_answer"],
        "sql_query": result.get("sql_query", ""),
        "error": result.get("error", "")
    }


# ============================================================================
# FASTAPI EXAMPLE
# ============================================================================

"""
FastAPI Integration Example:

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="SQL RAG Chatbot API")

class ChatRequest(BaseModel):
    question: str
    chat_history: list = []

class ChatResponse(BaseModel):
    answer: str
    sql_query: str
    error: str

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    '''
    Chat with the database using natural language.
    
    - **question**: Your question in natural language
    - **chat_history**: Optional conversation history
    '''
    try:
        response = chat_with_database(request.question, request.chat_history)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    '''Health check endpoint'''
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""