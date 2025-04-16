# simple_graph.py
from typing_extensions import TypedDict,Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage
from _langgraph.graph_factory import LangGraphFactory
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langgraph.types import Command
from langmem import create_manage_memory_tool,create_search_memory_tool
from langgraph.store.memory import InMemoryStore

# Define the state schema. Here we use a simple message list.
from langgraph.graph import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]

@tool(
        description=(
        "Cung cấp thông tin về thời tiết"
    ),
    response_format="content"
)
def get_weather():
    return "It's sunny today."

store = InMemoryStore(
    index={
        "dims": 1536,
        "embed": "openai:text-embedding-3-small",
    }
) 

tools=[
        # Memory tools use LangGraph's BaseStore for persistence (4)
        create_manage_memory_tool(namespace=("memories",)),
        create_search_memory_tool(namespace=("memories",)),
    ]



response_agent = create_react_agent(
            "gpt-4o",
            
            prompt="Bạn là một trợ lí AI, bạn có công cụ để quản lý và lưu trữ kí ức của tôi. Bạn sẽ nhận được câu hỏi bằng Tiếng Việt và bắt buộc phải trả lời bằng tiếng việt",
            # Use this to ensure the store is passed to the agent 
            # store=self.store
            tools = tools,
            store = store
        )

def build_simple_graph(graph: StateGraph) -> None:
    """
    Build a simple graph that chains a prompt with an LLM model.

    Args:
        graph (StateGraph): The graph to build.

    Returns:
        None
    """

    # Configure a real LLM instance.
    llm = ChatOpenAI(temperature=0.7, model="gpt-4o-mini", streaming=True)

    async def llm_node(state: State) -> State:
        """
        The LLM node that processes the messages.

        Args:
            state (State): The current state.

        Returns:
            State: The updated state.
        """
        messages = state["messages"]
        result = await llm.ainvoke(messages)
        return {"messages": [result]}
    

    # Add the node to the graph.
    def router(state: State) -> Command:
        goto =  "response_agent"
        return Command(goto = goto)
    graph.add_node("llm_node", llm_node)
    graph.add_node("response_agent", response_agent)
    graph.add_edge(START, "response_agent")

# Create a factory for our state schema.
factory = LangGraphFactory(state_schema=State)
# Compile the graph using our builder function.
async def get_compiled_graph() -> CompiledStateGraph:
    """
    Create a compiled graph using the simple graph builder.

    Returns:
        CompiledStateGraph: The compiled graph.
    """
    compiled_graph = await factory.create_graph(build_simple_graph)
    initial_state = {
        "messages": []
    }
    return response_agent, initial_state