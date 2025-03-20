import numpy as np
import sounddevice as sd

# Generate a 3-second beep (a 440 Hz tone)
duration = 3  # seconds
frequency = 440  # Hz
sample_rate = 48000
t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
audio = np.sin(2 * np.pi * frequency * t).astype(np.float32)

# Play the sound
sd.play(audio, sample_rate)
sd.wait()