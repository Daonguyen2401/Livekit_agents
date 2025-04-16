from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions,AutoSubscribe,JobRequest
from livekit.plugins import (
    openai,
    noise_cancellation,
    silero,
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from agent import MyAgent

load_dotenv()


# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(instructions="You are a helpful voice AI assistant.")


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    session = AgentSession(
        stt=openai.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=openai.TTS(),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    await session.start(
        room=ctx.room,
        agent=MyAgent(),
        # room_input_options=RoomInputOptions(
        #     noise_cancellation=noise_cancellation.BVC(),
        # ),
    )

    await session.generate_reply(
        instructions="Greet the user and offer your assistance."
    )

async def request_fnc(req: JobRequest):
# accept the job request
    await req.accept(
        # the agent's name (Participant.name), defaults to ""
        name="voice-agent",
        # the agent's identity (Participant.identity), defaults to "agent-<jobid>"
        identity="voice-agent",
        # attributes to set on the agent participant upon join
    )



if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint,request_fnc=request_fnc))