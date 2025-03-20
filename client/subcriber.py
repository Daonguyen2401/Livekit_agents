import asyncio
import logging
import numpy as np
import sounddevice as sd
from livekit import rtc, api
import threading
import time
import os

from dotenv import load_dotenv
load_dotenv(override=True)

room_name = os.getenv("ROOM_NAME")
print("room_name", room_name)

# Audio settings - use smaller buffer size for lower latency
SAMPLE_RATE = 48000
NUM_CHANNELS = 1
BLOCK_SIZE = 480  # Reduced from 960 to decrease latency

# Configure logging
logging.basicConfig(level=logging.INFO)

# Global variables
active_tracks = {}
output_stream = None
stream_lock = threading.Lock()
mixer_buffer = np.zeros((BLOCK_SIZE, NUM_CHANNELS), dtype=np.float32)

def audio_callback(outdata, frames, time, status):
    """Callback function for audio output stream"""
    if status:
        logging.warning(f"Audio status: {status}")
    
    # Clear the mixer buffer
    global mixer_buffer
    mixer_buffer.fill(0)
    
    # Mix all active tracks
    with stream_lock:
        active_count = 0
        for track_id, data in list(active_tracks.items()):
            # Get the most recent audio data, discard old data
            if len(data) > 0:
                # Only use the most recent frame to reduce latency
                audio_frame = data.pop(0)
                
                # Keep only a limited number of frames in buffer to prevent buildup
                if len(data) > 3:  # Keep only 3 frames max (60ms at 48kHz with 960 samples per frame)
                    data.clear()  # Clear all old data if we're falling behind
                    logging.warning(f"Buffer overflow for track {track_id}, discarding old data")
                
                # Convert to float32 if needed
                if audio_frame.dtype != np.float32:
                    audio_frame = audio_frame.astype(np.float32) / 32768.0
                
                # Ensure correct shape
                if len(audio_frame.shape) == 1:
                    audio_frame = audio_frame.reshape(-1, 1)
                
                # Match the frame size
                if audio_frame.shape[0] > frames:
                    audio_frame = audio_frame[:frames]
                elif audio_frame.shape[0] < frames:
                    # If frame is smaller, only mix what we have
                    mixer_buffer[:audio_frame.shape[0]] += audio_frame
                    active_count += 1
                    continue
                
                # Add to mixer buffer
                mixer_buffer += audio_frame
                active_count += 1
    
    # Scale if needed to prevent clipping
    if active_count > 1:
        max_val = np.max(np.abs(mixer_buffer))
        if max_val > 0.9:  # Scale if we're close to clipping
            mixer_buffer = mixer_buffer / max_val * 0.9
    
    # Copy mixed audio to output
    outdata[:] = mixer_buffer

def start_output_stream():
    """Start the audio output stream with low latency settings"""
    global output_stream
    
    if output_stream is not None:
        return
    
    # Use ASIO driver if available for lowest latency
    try:
        output_stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=NUM_CHANNELS,
            callback=audio_callback,
            blocksize=BLOCK_SIZE,
            dtype=np.float32,
            latency='low'  # Request low latency
        )
        output_stream.start()
        logging.info("Started low-latency audio output stream")
    except Exception as e:
        logging.error(f"Error starting audio stream: {e}")

def stop_output_stream():
    """Stop the audio output stream"""
    global output_stream
    if output_stream is not None:
        output_stream.stop()
        output_stream.close()
        output_stream = None
        logging.info("Stopped audio output stream")

# Print available audio devices
def list_audio_devices():
    print("Available audio devices:")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        print(f"[{i}] {device['name']} (Max output channels: {device['max_output_channels']})")
    return devices

async def process_audio_track(track: rtc.Track):
    """Process audio from a LiveKit track with minimal buffering"""
    track_id = track.sid
    
    # Initialize track buffer
    with stream_lock:
        active_tracks[track_id] = []
    
    # Start output stream if not already running
    start_output_stream()
    
    # Create audio stream
    audio_stream = rtc.AudioStream(track)
    
    try:
        async for eventFrame in audio_stream:
            event = eventFrame.frame
            
            if hasattr(event, 'data') and event.data:
                # Convert PCM data to numpy array
                pcm_data = np.frombuffer(event.data, dtype=np.int16)
                
                # Add to track buffer
                with stream_lock:
                    # Only add if we don't already have too many frames buffered
                    if track_id in active_tracks and len(active_tracks[track_id]) < 3:
                        active_tracks[track_id].append(pcm_data)
    except Exception as e:
        logging.error(f"Error processing audio for track {track_id}: {e}")
    finally:
        # Remove track when done
        with stream_lock:
            if track_id in active_tracks:
                del active_tracks[track_id]
        
        # If no more active tracks, stop output stream
        if len(active_tracks) == 0:
            stop_output_stream()
        
        logging.info(f"Audio processing ended for track: {track_id}")

def on_track_subscribed(
    track: rtc.Track,
    publication: rtc.TrackPublication,
    participant: rtc.RemoteParticipant,
):
    print(f"Track subscribed: {track.kind} from {participant.identity}")

    if participant.identity== "voice-agent":
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            asyncio.create_task(process_audio_track(track))
        else:
            logging.info(f"Not processing non-audio track: {track.kind}")

def on_participant_disconnected(participant: rtc.RemoteParticipant):
    logging.info(f"Participant disconnected: {participant.identity}")
    # Cleanup is handled in the process_audio_track function

def setup_room_handlers(room):
    room.on("track_subscribed", on_track_subscribed)
    room.on("participant_disconnected", on_participant_disconnected)
    print("Room event handlers set")

async def main():
    # List available audio devices
    devices = list_audio_devices()
    
    try:
        # Connect to LiveKit room
        room = rtc.Room()
        setup_room_handlers(room)
        
        # Create access token
        token = (
            api.AccessToken()
            .with_identity("python-listener")
            .with_name("Python Listener")
            .with_grants(api.VideoGrants(room_join=True, room=room_name))
            .to_jwt()  # Replace with your API credentials
        )
        
        # Connect to LiveKit
        await room.connect(
            "wss://demo-smart-mirror-jxj34x8q.livekit.cloud", 
            token, 
            options=rtc.RoomOptions(auto_subscribe=True)
        )
        logging.info("Connected to LiveKit room")
        
        # Keep the program running
        await asyncio.Future()
    except Exception as e:
        logging.error(f"Error in main: {e}")
    finally:
        # Clean up
        stop_output_stream()
        with stream_lock:
            active_tracks.clear()
        logging.info("Cleanup complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Program terminated by user")