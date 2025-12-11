#!/usr/bin/env python3
"""
Example helper script to compute sample rate, N, and generate a float64 buffer for a sine wave for NI PXIe-4468.
This script is for verification only — it uses pure Python and numpy to compute the buffer you will generate in LabVIEW.
"""
import math
import numpy as np

FREQUENCIES = [60, 120, 8192, 29430]  # Hz
DEVICE_MAX = 200_000  # S/s
AMPLITUDE = 1.0  # V peak
CYCLES_IN_BUFFER = 4
PHYSICAL_CHANNEL = 'Dev1/ao0'

def compute_N_and_samplerate(freq, device_max=DEVICE_MAX):
    maxN = int(math.floor(device_max / freq))
    if maxN < 2:
        raise ValueError(f'Frequency {freq} Hz is too high for device max {device_max} S/s')
    N = maxN
    samplerate = freq * N
    return N, samplerate

def generate_buffer(freq, amplitude=AMPLITUDE, device_max=DEVICE_MAX, cycles=CYCLES_IN_BUFFER):
    N, sr = compute_N_and_samplerate(freq, device_max)
    buffer_samples = N * cycles
    t = np.arange(buffer_samples) / sr
    buffer = amplitude * np.sin(2 * np.pi * freq * t)
    return buffer, N, sr

if __name__ == '__main__':
    for f in FREQUENCIES:
        try:
            buf, N, sr = generate_buffer(f)
            print(f'Frequency: {f} Hz -> N={N}, SampleRate={sr} S/s, BufferSamples={len(buf)}')
            print(f'First 8 samples: {np.round(buf[:8], 6).tolist()}')
            print('---')
        except ValueError as e:
            print('ERROR:', e)
