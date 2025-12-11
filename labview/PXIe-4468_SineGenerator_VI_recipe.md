# PXIe-4468 Sine Generator — LabVIEW 2025 Recipe

Goal
----
Create a LabVIEW 2025 VI that continuously outputs a pure tone on a single AO channel of an NI PXIe-4468. The VI must: use a dropdown with the frequencies [60, 120, 8192, 29430] Hz, compute the largest integer samples-per-cycle N such that sampleRate = frequency * N <= deviceMax (200000 S/s), generate a seamless sine buffer, and run continuous generation. Amplitude = 1.0 V (peak). Default AO channel: Dev1/ao0.

Front Panel Controls / Indicators
-------------------------------
- Ring (dropdown) — name: Frequency (Hz) — items: 60, 120, 8192, 29430 (display values are numeric).
- Numeric control (read-only) — name: Computed Sample Rate (S/s) — shows the computed sample rate.
- Numeric control (read-only) — name: Samples Per Cycle (N) — integer.
- Ring (dropdown) — name: Physical Channel — items: Dev1/ao0, Dev1/ao1, Dev1/ao2, Dev1/ao3, Dev1/ao4, Dev1/ao5, Dev1/ao6, Dev1/ao7 (default: Dev1/ao0).
- Numeric control — name: Device Max Sample Rate (S/s) — default 200000.
- Numeric control — name: Amplitude (V peak) — default 1.0.
- Boolean button — name: Start.
- Boolean button — name: Stop.
- Error in/out cluster — standard DAQmx error handling.

Block Diagram Overview
----------------------
1) **Main While Loop and Event Structure**:
   
   **While Loop Configuration:**
   - Place a While Loop on the block diagram (this will be your main execution loop).
   - Wire the Stop button (inverted with a NOT gate) to the conditional terminal (red circle on bottom-right of loop).
   - The loop continues running while Stop = FALSE, and exits when Stop = TRUE.
   
   **Event Structure Inside the While Loop:**
   - Place an Event Structure inside the While Loop.
   - Right-click the Event Structure border → "Edit Events" to configure event cases:
   
   **Event Case 1: "Frequency: Value Change"**
   - Trigger: When user selects a new frequency from the Frequency (Hz) ring.
   - Purpose: Recalculate sample rate, regenerate sine buffer, and restart DAQmx task with new parameters.
   - This is where the main signal generation logic lives (see step 2 below).
   
   **Event Case 2: "Physical Channel: Value Change"** (optional but recommended)
   - Trigger: When user selects a different AO channel.
   - Purpose: Stop current task, recreate with new channel, restart generation.
   - Can combine this with Frequency event or handle separately for clarity.
   
   **Event Case 3: "Start: Value Change"** (optional)
   - Trigger: When Start button is pressed.
   - Purpose: Manually start generation if not auto-starting on frequency change.
   - Useful if you want explicit user control over when output begins.
   
   **Event Case 4: "Timeout"** (optional, use if implementing continuous buffer refill)
   - Set timeout value (e.g., 500 ms or -1 for no timeout if not using).
   - Purpose: Periodically write new data to the DAQmx buffer if implementing a producer-consumer pattern.
   - **For this VI with hardware regeneration, timeout is NOT mandatory** — writing once with continuous timing is sufficient.
   - If using timeout for status updates only, set it to 1000 ms and keep the case empty or add status indicators.
   
   **Event Structure Best Practices:**
   - Use the "Filter" event node to prevent events from queuing up while processing.
   - Include error handling in each event case.
   - If no timeout case is needed, set Event Structure timeout to -1 (wait indefinitely).
   
   **Execution Flow:**
   - Loop starts → Event Structure waits for an event
   - User changes Frequency → "Frequency: Value Change" case executes
   - Case completes → Loop iterates back to Event Structure
   - Loop continues until Stop button pressed
   - On Stop: Exit loop → Execute cleanup code outside loop (DAQmx Stop/Clear)

2) **On Frequency Value Change Event (Main Logic):**
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

