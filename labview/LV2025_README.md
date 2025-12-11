# LabVIEW 2025 PXIe-4468 Sine Generator (Recipe files)

This folder contains a LabVIEW 2025 project template and a detailed step-by-step recipe to create a ready-to-import VI that:

- Provides a front panel dropdown of frequencies (60 Hz, 120 Hz, 8192 Hz, 29430 Hz).
- Automatically computes an integer samples-per-cycle (N) to use the largest N such that sampleRate = frequency * N <= deviceMax (200000 S/s).
- Generates a sine buffer for continuous generation on a single AO channel (default: Dev1/ao0) with amplitude +/-1 V.
- Reconfigures/output on dropdown value change for continuous generation.

Notes:
- This repo entry does NOT include a compiled .vi binary. Instead, it contains a complete build recipe you can follow in LabVIEW 2025 to produce the VI quickly.
- The recipe also includes a small Python example that computes sample rate and demonstrates how to programmatically compute the buffer (useful for verifying values before building the VI).

Files included in this folder:
- PXIe-4468_SineGenerator_VI_recipe.md  : Complete front-panel and block-diagram wiring steps.
- example_python/control_sine_ni4468.py  : Python helper to compute sample rates and example buffer generation using nidaqmx (for verification).

If you want me to add a binary .vi file to a PR instead of a recipe, tell me and I will create a PR including the binary.