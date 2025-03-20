import asyncio
from dotenv import load_dotenv
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm, JobRequest
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import openai, silero
from livekit import rtc
from api import AssistantFnc

load_dotenv()

async def entrypoint(ctx: JobContext):
    # Connect to the room without auto-subscribing to all tracks
    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_NONE)

    chat_ctx = llm.ChatContext()
    chat_ctx.append(
        role="system",
        text=(
            "You are a voice assistant created by LiveKit. Your interface with users will be voice. "
            "You should use short and concise responses, and avoid usage of unpronounceable punctuation. "
            "Always respond in Vietnamese, regardless of the language used by the user. "
            "Your responses should be natural and conversational Vietnamese"
        )
    )

    

    # Initialize the VoiceAssistant
    fnc_ctx = AssistantFnc()  # Assuming this is defined elsewhere
    assistant = VoiceAssistant(
        vad=silero.VAD.load(),
        stt=openai.STT(langguage="vi"),
        llm=openai.LLM(),
        tts=openai.TTS(voice="alloy", langguage="vi"),
        chat_ctx=chat_ctx,
        fnc_ctx=fnc_ctx,
    )

    # Start the assistant with the room
    assistant.start(ctx.room)

    # Say an initial greeting
    await asyncio.sleep(1)
    await assistant.say("Hey, how can I help you today!", allow_interruptions=True)

    # Define the synchronous callback for track subscription
    def on_track_subscribed(track: rtc.AudioTrack, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        print("Track first subcribe")
        if participant.identity == "python-publisher":  # Adjust this condition
            print(f"Subscribed to audio publisher track: {publication.sid}")
            # Run the async handling in the event loop
            asyncio.create_task(handle_audio_track(track, assistant))

    # Define the async function to handle the audio track
    async def handle_audio_track(track: rtc.AudioTrack, assistant: VoiceAssistant):
        audio_stream = rtc.AudioStream(track)
        assistant._pipeline._input_stream.stream(audio_stream)  # Feed the track to the assistant

    # Register the synchronous callback
    ctx.room.on("track_subscribed", on_track_subscribed)

async def request_fnc(req: JobRequest):
# accept the job request
    await req.accept(
        # the agent's name (Participant.name), defaults to ""
        name="voice-agent",
        # the agent's identity (Participant.identity), defaults to "agent-<jobid>"
        identity="voice-agent",
        # attributes to set on the agent participant upon join
    )

    # or reject it
    # await req.reject()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint,request_fnc= request_fnc))