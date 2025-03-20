# agent.py
import logging
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobRequest,
    WorkerOptions,
    cli,
    metrics,
)
import asyncio
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, silero
from _langgraph.graph_wrapper import LivekitGraphRunner  # our wrapper that adapts a compiled graph to LiveKit
from _langgraph.graphs.simple_graph import get_compiled_graph
from livekit import rtc
logger = logging.getLogger("voice-agent")


async def entrypoint(ctx: JobContext):
    
    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_NONE)

    participant = await ctx.wait_for_participant()
    logger.info(f"starting voice assistant for participant {participant.identity}")

    # Get the compiled graph and create a LiveKitGraphRunner instance, this instance is the one responsible for running the graph.
    # The LiveKitGraphRunner is a wrapper that adapts a compiled graph from LangGraph to be compliant with LiveKit's LLM interface.
    compiled_graph, initial_state = await get_compiled_graph()
    graph_runner = LivekitGraphRunner(compiled_graph, initial_state)
    
    agent = VoicePipelineAgent(
        vad=silero.VAD.load(),
        stt=openai.stt.STT(
            language="vi"
        ),
        llm=graph_runner,  # using our wrapped LangGraph for inference
        tts=openai.tts.TTS(),
        min_endpointing_delay=0.5,
        max_endpointing_delay=5.0,
    )

    usage_collector = metrics.UsageCollector()
    @agent.on("metrics_collected")
    def on_metrics_collected(agent_metrics: metrics.AgentMetrics):
        """
        On metrics collected

        Args:
            agent_metrics (metrics.AgentMetrics): The agent metrics.

        Returns:
            None

        This method logs the agent metrics and collects usage metrics.
        """
        metrics.log_metrics(agent_metrics)
        usage_collector.collect(agent_metrics)

    # Start the agent and say the welcome message.
    agent.start(ctx.room, participant)
    await agent.say("Hey, how can I help you today?", allow_interruptions=True)

    # Define the synchronous callback for track subscription
    def on_track_subscribed(track: rtc.AudioTrack, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print("Track first subcribe")
        if participant.identity == "python-publisher":  # Adjust this condition
            print(f"Subscribed to audio publisher track: {publication.sid}")
            # Run the async handling in the event loop
            asyncio.create_task(handle_audio_track(track, agent))

    # Define the async function to handle the audio track
    async def handle_audio_track(track: rtc.AudioTrack, agent: VoicePipelineAgent):
        audio_stream = rtc.AudioStream(track)
        agent._pipeline._input_stream.stream(audio_stream)  # Feed the track to the assistant

    # Register the synchronous callback
    ctx.room.on("track_subscribed", on_track_subscribed)

async def request_fnc(req: JobRequest):

    await req.accept(
        
        name="voice-agent",
        identity="voice-agent",
    )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            request_fnc=request_fnc,
        ),
    )
