"""Writes chime.wav beside this file: cook mode's timer sound, two soft bell tones made here, so the app needs no
sound from anywhere else (and no licence for one). Run with any Python 3: python makeChime.py"""
import math
import struct
import wave
from pathlib import Path

RATE = 22050
LENGTH = 1.4


def bell(t, frequency, start):
    """A struck tone: a quick rise, then a long fade."""
    if t < start:
        return 0.0
    s = t - start
    return math.sin(2 * math.pi * frequency * s) * math.exp(-4.0 * s) * (1 - math.exp(-200 * s))


samples = []
for i in range(int(RATE * LENGTH)):
    t = i / RATE
    value = 0.45 * bell(t, 1318.5, 0.0) + 0.45 * bell(t, 1975.5, 0.18) + 0.1 * bell(t, 2637.0, 0.0)
    samples.append(int(max(-1.0, min(1.0, value)) * 30000))

with wave.open(str(Path(__file__).with_name("chime.wav")), "wb") as out:
    out.setnchannels(1)
    out.setsampwidth(2)
    out.setframerate(RATE)
    out.writeframes(struct.pack(f"<{len(samples)}h", *samples))
