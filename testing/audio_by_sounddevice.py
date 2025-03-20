import sounddevice as sd
import numpy as np
from scipy.io import wavfile
import time
from pynput import keyboard

# Audio recording settings
FORMAT = np.int16  # 16-bit integer samples
CHANNELS = 1
RATE = 44100
CHUNK = 1024

recording = False
frames = []
stream = None

def callback(indata, frames_count, time_info, status):
    """Callback function to collect audio data."""
    if recording:  # Only append data if recording is active
        frames.append(indata.copy())

def start_recording():
    global recording, frames
    if not recording:
        recording = True
        frames = []  # Reset frames for a new recording
        print("Recording...")

def stop_recording():
    global recording, frames
    if recording:
        recording = False
        print("Finished recording")
        if frames:  # Check if frames is not empty
            audio_data = np.concatenate(frames, axis=0)
            timestamp = int(time.time())
            filename = f"recorded_{timestamp}.wav"
            wavfile.write(filename, RATE, audio_data)
            print(f"Audio saved as {filename}")
        else:
            print("No audio data recorded.")

def on_press(key):
    if key == keyboard.Key.space:
        start_recording()

def on_release(key):
    if key == keyboard.Key.space:
        stop_recording()
    elif key == keyboard.Key.esc:
        print("Exiting...")
        return False

# Initialize the stream once at startup
print("Initializing audio stream...")
stream = sd.InputStream(samplerate=RATE, channels=CHANNELS, dtype=FORMAT,
                        blocksize=CHUNK, device=4,  # Replace 4 with your device index
                        callback=callback)
stream.start()

# Set up the keyboard listener
try:
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        print("Press and hold SPACE to record audio, release to stop. Press ESC to exit.")
        listener.join()
finally:
    # Cleanup: Stop and close the stream when exiting
    if stream:
        stream.stop()
        stream.close()
        print("Audio stream closed.")