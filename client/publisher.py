import asyncio
import logging
from signal import SIGINT, SIGTERM
import os
import numpy as np
from livekit import rtc, api
import sounddevice as sd
from pynput import keyboard
import time
from scipy.io import wavfile

from dotenv import load_dotenv
load_dotenv(override=True)

# Audio settings matching LiveKit requirements
SAMPLE_RATE = 48000  # Hz
NUM_CHANNELS = 1
SAMPLES_PER_FRAME = 480  # 10ms at 48kHz
FORMAT = np.int16  # 16-bit integer samples

# Global variables
recording = False
recorded_frames = []  # Store frames for WAV file
stream = None
listener = None
exit_flag = False
audio_source = None  # Global audio source
event_loop = None  # Global event loop reference
last_frame_time = 0  # Track when last frame was sent to avoid duplicates

print("API Key:", os.getenv("LIVEKIT_API_KEY"))
print("API Secret:", os.getenv("LIVEKIT_API_SECRET"))
print("URL:", os.getenv("LIVEKIT_URL"))

room_name = os.getenv("ROOM_NAME")
print("room_name", room_name)

def audio_callback(indata, frames_count, time_info, status):
    """Callback function to handle audio data from sounddevice and send to LiveKit."""
    global last_frame_time
    
    if status:
        # Print any errors or issues
        logging.warning(f"Status in audio callback: {status}")
    
    # Avoid duplicate frames which can cause echo
    current_time = time.time() * 1000  # Convert to milliseconds
    time_diff = current_time - last_frame_time
    
    # Ensure we're not sending frames too rapidly (should be ~10ms intervals for 48kHz)
    # This helps prevent potential echo caused by frame duplication
    if time_diff < 8:  # Less than 8ms since last frame
        return
    
    last_frame_time = current_time
    
    # Only store for WAV file when recording (SPACE pressed)
    if recording:
        audio_data = indata.copy()
        recorded_frames.append(audio_data)
    
    # Always send audio to LiveKit (silent frames when not recording)
    if audio_source and event_loop:
        # Use actual audio data when recording, otherwise use silence
        frame_data = indata if recording else np.zeros_like(indata)
        
        # Create LiveKit audio frame
        audio_frame = rtc.AudioFrame(
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            samples_per_channel=frame_data.shape[0],
            data=frame_data.tobytes()
        )
        
        # Send to LiveKit asynchronously
        asyncio.run_coroutine_threadsafe(
            audio_source.capture_frame(audio_frame), 
            event_loop
        )

def save_wav_file():
    """Save the recorded audio to a WAV file."""
    if not recorded_frames:
        logging.warning("No audio frames to save")
        return

    # Create a filename with timestamp
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"recording-{timestamp}.wav"
    
    try:
        # Combine all audio frames
        all_audio = np.concatenate(recorded_frames)
        
        # Save using wavfile.write from scipy.io
        wavfile.write(filename, SAMPLE_RATE, all_audio)
        logging.info(f"Recording saved to {filename}")
        
        # Clear the recorded frames for next recording
        recorded_frames.clear()
    except Exception as e:
        logging.error(f"Error saving WAV file: {e}")

def on_press(key):
    """Start recording when SPACE is pressed."""
    global recording
    if key == keyboard.Key.space and not recording:
        recording = True
        recorded_frames.clear()  # Clear previous recording
        logging.info("Recording started... (streaming to LiveKit and recording)")

def on_release(key):
    """Stop recording when SPACE is released, exit on ESC."""
    global recording, exit_flag
    if key == keyboard.Key.space and recording:
        recording = False
        logging.info("Recording stopped.")
        #save_wav_file()  # Save the recording when space is released
    elif key == keyboard.Key.esc:
        logging.info("Exiting...")
        exit_flag = True
        return False

async def main(room: rtc.Room):
    """Connect to LiveKit room and publish audio track."""
    global audio_source
    
    # Generate access token
    token = (
        api.AccessToken()
        .with_identity("python-publisher")
        .with_name("Python Publisher")
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )
    url = os.getenv("LIVEKIT_URL")
    
    if not url:
        logging.error("LIVEKIT_URL environment variable is not set")
        return
    
    print("Token", token)

    # Connect to the room
    logging.info("Connecting to %s", url)
    try:
        await room.connect(url, token, options=rtc.RoomOptions(auto_subscribe=True))
        logging.info("Connected to room %s", room.name)
    except rtc.ConnectError as e:
        logging.error("Failed to connect to the room: %s", e)
        return

    # Create audio source with echo cancellation settings
    audio_source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS)
    
    # Create track with echo cancellation enabled
    track = rtc.LocalAudioTrack.create_audio_track("mic-audio", audio_source)
    
    # Enable acoustic echo cancellation if it's available in your version of LiveKit
    options = rtc.TrackPublishOptions(
        source=rtc.TrackSource.SOURCE_MICROPHONE,
        # Set additional options for audio processing
        # These might vary depending on your LiveKit version
        dtx=True,  # Discontinuous transmission
        red=1      # Redundancy encoding
    )
    
    try:
        publication = await room.local_participant.publish_track(track, options)
        logging.info("Published track %s", publication.sid)
    except Exception as e:
        logging.error(f"Failed to publish track: {e}")
        return
    
    # Keep the task running
    while not exit_flag:
        await asyncio.sleep(0.1)

async def cleanup(room, loop):
    """Clean up resources on exit."""
    global stream, listener
    await room.disconnect()
    if stream:
        stream.stop()
        stream.close()
        logging.info("Audio stream closed.")
    if listener:
        listener.stop()
        logging.info("Keyboard listener stopped.")
    loop.stop()
    logging.info("Event loop stopped.")

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        handlers=[logging.FileHandler("mic_to_livekit.log"), logging.StreamHandler()]
    )

    # List available audio devices to help debug
    logging.info("Available audio devices:")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        logging.info(f"Device {i}: {device['name']}")

    # Get event loop reference
    event_loop = asyncio.get_event_loop()
    
    # Setup LiveKit room
    room = rtc.Room(loop=event_loop)

    # Setup sounddevice stream
    try:
        # Try to use default device first
        device_idx = None
        
        # Use latency setting to help reduce echo
        latency = 'low'  # Use low latency setting
        
        # Explicitly test if we can open the stream
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=NUM_CHANNELS,
            dtype=FORMAT,
            blocksize=SAMPLES_PER_FRAME,
            callback=audio_callback,
            device=device_idx,  # Set to your microphone device index if needed
            latency=latency     # Use low latency to reduce echo
        )
        stream.start()
        logging.info(f"Audio stream initialized and started with device: {device_idx if device_idx is not None else 'default'}")
    except Exception as e:
        logging.error(f"Error initializing audio stream: {e}")
        
        # Try to find a working input device
        found_device = False
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                try:
                    logging.info(f"Trying device {i}: {device['name']}")
                    stream = sd.InputStream(
                        samplerate=SAMPLE_RATE,
                        channels=NUM_CHANNELS,
                        dtype=FORMAT,
                        blocksize=SAMPLES_PER_FRAME,
                        callback=audio_callback,
                        device=i,
                        latency=latency  # Use low latency to reduce echo
                    )
                    stream.start()
                    logging.info(f"Successfully initialized audio with device {i}: {device['name']}")
                    found_device = True
                    break
                except Exception as e2:
                    logging.warning(f"Failed to use device {i}: {e2}")
        
        if not found_device:
            logging.error("Could not find a working audio input device. Exiting.")
            exit(1)

    # Setup keyboard listener
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    logging.info("Keyboard listener started. Press SPACE to start streaming to LiveKit.")
    logging.info("Release SPACE to stop streaming and save recording to WAV file. Press ESC to exit.")

    # Handle signals for cleanup
    async def signal_handler():
        global exit_flag
        exit_flag = True
        await cleanup(room, event_loop)

    for sig in [SIGINT, SIGTERM]:
        event_loop.add_signal_handler(sig, lambda: asyncio.ensure_future(signal_handler()))

    # Start the main function
    task = asyncio.ensure_future(main(room))
    
    try:
        event_loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if not exit_flag:
            asyncio.run_coroutine_threadsafe(cleanup(room, event_loop), event_loop).result()
        event_loop.close()
        logging.info("Program terminated.")