from typing import Callable, Dict, Any, List, Optional, Union
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langchain_core.runnables import Runnable
from _langgraph.nodes.base_node import BaseNode
from _langgraph.base_state import BaseState
import logging
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)


class AgentNode(BaseNode):
    """
    An LLM node that processes conversation messages and generates a response using an LLM.
    The node now receives a model and a list of tools so that it can bind the tools to the model.
    """
    # model: ChatOpenAI
    tools: Optional[List[Callable[[Union[Callable, Runnable]], BaseTool]]] = None
    store: Any = None

    # agent_system_prompt_memory = """
    #     < Role >
    #     You are a helpful assistant. who can store user memory
    #     </ Role >

    #     < Tools >
    #     You have access to the following tools to help manage user memory:

    #     1. manage_memory - Store any relevant information about contacts, actions, discussion, etc. in memory for future reference
    #     2. search_memory - Search for any relevant information that may have been stored in memory
    #     </ Tools >

    #     """
    

    async def run(self, state: BaseState) -> Dict[str, Any]:
        messages = state.messages
        
        response_agent = create_react_agent(
            "gpt-4o",
            tools=self.tools,
            prompt="Bạn là một trợ lí AI, bạn có công cụ để quản lý và lưu trữ kí ức của tôi. Bạn sẽ nhận được câu hỏi bằng Tiếng Việt và bắt buộc phải trả lời bằng tiếng việt",
            # Use this to ensure the store is passed to the agent 
            store=self.store
)
        
        # Asynchronously invoke the chain.
        result = await response_agent.invoke({"messages": messages})
        
        # Get the last message (the response)
        response_message = result["messages"][-1]
        
        # Modify the state directly rather than creating a new state
        # This avoids the "Channel already exists" error
        state.messages.append(response_message)
        
        # Return the modified state
        return state
