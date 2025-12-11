# PXIe-4468 Sine Generator — LabVIEW 2025 Recipe

Goal
----
Create a LabVIEW 2025 VI that continuously outputs a pure tone on a single AO channel of an NI PXIe-4468. The VI must: use a dropdown with the frequencies [60, 120, 8192, 29430] Hz, compute the largest integer samples-per-cycle N such that sampleRate = frequency * N <= deviceMax (200000 S/s), generate a seamless sine buffer, and run continuous generation. Amplitude = 1.0 V (peak). Default AO channel: Dev1/ao0.

Front Panel Controls / Indicators
-------------------------------
- Ring (dropdown) — name: Frequency (Hz) — items: 60, 120, 8192, 29430 (display values are numeric).
- Numeric control (read-only) — name: Computed Sample Rate (S/s) — shows the computed sample rate.
- Numeric control (read-only) — name: Samples Per Cycle (N) — integer.
- String control — name: Physical Channel (default "Dev1/ao0").
- Numeric control — name: Device Max Sample Rate (S/s) — default 200000.
- Numeric control — name: Amplitude (V peak) — default 1.0.
- Boolean button — name: Start.
- Boolean button — name: Stop.
- Error in/out cluster — standard DAQmx error handling.

Block Diagram Overview
----------------------
1) Use a While Loop that runs until Stop pressed. Inside the while loop use an Event Structure configured for:
   - Value Change on the Frequency ring (and optionally the Start button).
   - Timeout event: used to service continuous writes if you prefer continuous refill (not mandatory).

2) On Frequency Value Change:
   - Read the selected frequency f (double).
   - Read DeviceMax (default 200000), Amplitude, Physical Channel.
   - Compute maxN = floor(DeviceMax / f).
   - If maxN < 2 -> raise an error: "Frequency too high for device max sample rate".
   - Else set N = maxN. (This is "largest integer N")
   - Compute sampleRate = f * N. Update indicators (Sample Rate and N).

3) Create waveform buffer:
   - Choose cyclesInBuffer = 4 (makes buffer length = N * cyclesInBuffer). Using multiple cycles reduces CPU churn while keeping seamless loop.
   - bufferSamples = N * cyclesInBuffer.
   - Use a For Loop (i = 0..bufferSamples-1) and compute: sampleValue[i] = Amplitude * sin(2*pi*f * i / sampleRate).
   - Build a 1D array of double (AnalogF64) with length bufferSamples.

4) DAQmx configuration and write:
   - If a previous DAQmx Task ref exists, stop and clear it before re-creating.
   - DAQmx Create Virtual Channel (Analog Output — Voltage) with Physical Channel from control. Voltage range: -Amplitude..Amplitude.
   - DAQmx Timing: Sample Clock, Rate = sampleRate, Continuous Samples, Samples per Channel = bufferSamples.
   - DAQmx Write (AnalogF64) with autoStart = TRUE (or use DAQmx Start Task separately).
   - For continuous generation you can either: write the buffer once (DAQmx will cycle it if configured as continuous and hardware supports regeneration) or implement a producer/consumer pattern that keeps writing the buffer ahead of the output. For the 4468, hardware regeneration is supported for AO streams — writing once with continuous timing is sufficient if you choose a buffer that fits device memory and regeneration is enabled.

5) Start generation: start the task and update UI.

6) On Start button: if task ready, start; On Stop: DAQmx Stop and DAQmx Clear and release resources.

DAQmx VI list (use LabVIEW 2025 DAQmx palette)
------------------------------------------------
- DAQmx Create Virtual Channel (Analog Output – Voltage)
- DAQmx Timing (Sample Clock)
- DAQmx Write (AnalogF64) — array input
- DAQmx Start Task (optional if Write auto-starts)
- DAQmx Stop
- DAQmx Clear

Implementation details and hints
--------------------------------
- Integer N selection: using the largest integer N = floor(DeviceMax / f) guarantees the largest samples-per-cycle while keeping sampleRate <= deviceMax. This gives maximum waveform fidelity for that device rate.
- Buffer cyclesInBuffer: 4 cycles is a sensible default. You can expose cyclesInBuffer as a front-panel control if you want longer buffers for lower CPU usage.
- Buffer length must be an integer number of cycles to avoid discontinuities.
- Use DAQmx property nodes if you need to set regeneration behavior (on newer DAQmx versions the driver accepts regenerated buffers by default).
- If you need glitch-free frequency switching, use a double-buffer approach: prepare the new buffer, wait for a safe boundary (optional), then swap buffers quickly or reconfigure the task between runs. Simpler: stop, clear, recreate task and start with the new buffer.

Default values for this recipe
-----------------------------
- Frequencies: [60, 120, 8192, 29430] Hz
- Device Max Sample Rate: 200000 S/s
- Amplitude: 1.0 V (peak)
- Physical Channel: Dev1/ao0
- cyclesInBuffer: 4

Verification
------------
- Use the included Python helper to compute N and the sample rate for your frequency list and inspect the generated buffer values before building the VI.

Files to add to your LabVIEW project (manual steps)
---------------------------------------------------
- Create a new LabVIEW Project (LabVIEW 2025).
- Add a new VI named "PXIe-4468_SineGenerator.vi".
- Build the front panel controls/indicators exactly as listed above.
- Implement the block diagram following the steps in this document.
- Save the VI and project.

If you want, I can also:
- produce an actual .vipc/.lvproj skeleton with empty VIs committed,
- or generate a PR that contains a binary .vi file (you will need to accept adding binary files to the repo).

