import httpx
import requests
from livekit.agents import function_tool, Agent, RunContext

# url = "https://7ad6-1-53-240-222.ngrok-free.app/webhook/invoke_chat"

url = "https://ce5f-1-53-240-222.ngrok-free.app/webhook/invoke_chat"

class MyAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="You are a helpful voice AI assistant.")

    @function_tool()
    async def response_user(
        self,
        context: RunContext,
        userinput: str,
    ) -> dict:
        """Answer all user question with this tool, use the result to send back to user directly
        
        Args:
            userinput: the users question or command.
        """
        params = {
            "chatInput": userinput
        }
        
        response = requests.get(
            url,
            params=params,
        )
        # if response.status_code == 200:

        #     context.session.say(
        #         "I cannot help you with that",
        #         allow_interruptions=False,
        #     )
        # else:
        #     context.session.say(
        #         response["output"],
        #         allow_interruptions=False,
        #     )
        data = response.json()
        output = data.get("output")
        print(output)
        return {"AI_response": output}
        