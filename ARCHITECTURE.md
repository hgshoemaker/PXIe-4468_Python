# System Architecture

## Application Structure

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                              │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              PXIeControlGUI (tkinter)                   │ │
│  │  - Tabbed interface for 4 cards                        │ │
│  │  - Frequency selector                                   │ │
│  │  - Channel enable/disable controls                      │ │
│  │  - Amplitude inputs (µV)                               │ │
│  │  - Start/Stop buttons                                   │ │
│  │  - Real-time input monitoring (RMS/Peak)               │ │
│  │  - Oscilloscope launcher buttons                        │ │
│  └───────────────────┬────────────────────────────────────┘ │
│                      │                                       │
│  ┌───────────────────▼────────────────────────────────────┐ │
│  │         OscilloscopeWindow (matplotlib)                 │ │
│  │  - Real-time waveform display                          │ │
│  │  - Clipping detection (±10V)                          │ │
│  │  - Adjustable time span and Y-scale                    │ │
│  │  - Freeze function                                      │ │
│  │  - Signal statistics (RMS/Peak/Freq)                   │ │
│  └───────────────────┬────────────────────────────────────┘ │
│                      │                                       │
│  ┌───────────────────▼────────────────────────────────────┐ │
│  │           FrequencyManager                              │ │
│  │  - Loads frequencies.CSV                               │ │
│  │  - Calculates optimal sample rates                     │ │
│  │  - Returns quality metrics                             │ │
│  └───────────────────┬────────────────────────────────────┘ │
│                      │                                       │
│  ┌───────────────────▼────────────────────────────────────┐ │
│  │           MultiCardGenerator                            │ │
│  │  - Manages 4 PXIe-4468 cards (SV1-SV4)               │ │
│  │  - 8 total channels (2 per card: AO0-AO1)            │ │
│  │  - Analog output (AO) and input (AI) tasks           │ │
│  │  - Thread-safe configuration                           │ │
│  │  - Background worker thread                            │ │
│  │  - Real-time AI monitoring (RMS/Peak)                 │ │
│  │  - Oscilloscope data buffering (5000 samples)         │ │
│  │                                                         │ │
│  │  ChannelConfig objects:                                │ │
│  │  [SV1/AO0-1] [SV2/AO0-1] [SV3/AO0-1] [SV4/AO0-1]    │ │
│  └─────────────────│  AO0/AO1 → RF Amplifier → AI0/AI1
                     │
                     ──┬────────────────────────────────────┘ │
│                      │                                       │
│  ┌───────────────────▼────────────────────────────────────┐ │
│  │               NI-DAQmx Tasks                            │ │
│  │  - AO Task: Continuous waveform generation            │ │
│  │  - AI Task: Continuous analog input monitoring        │ │
│  │  - Large AI buffers (2 seconds) prevent overflow      │ │
│  │  - Fast read rate (50 reads/second)                   │ │
│  │  - Individual amplitudes per channel                   │ │
│  └───────────────────┬────────────────────────────────────┘ │
└────────────────────┬─┴─────────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────┐
        │   PXIe Chassis (Thunderbolt)│
        │                             │
        │  ┌──────┐  ┌──────┐        │
        │  │ SV1  │  │ SV2  │        │
        │  │4468  │  │4468  │        │
        │  └──────┘  └──────┘        │
        │  ┌──────┐  ┌──────┐        │
        │  │ SV3  │  │ SV4  │        │
        │  │4468  │  │4468  │        │
        │  └──────┘  └──────┘        │
        └─────────────────────────────┘
```

## Data Flow8 ChannelConfig objects (2 per card)
    ↓
GUI displays with 4 tabs (SV1-SV4)
    ↓
Each tab shows 2 channels (AO0-AO1) with input monitoring
```
User runs main.py
    ↓
connect_to_chassis()
    ↓
Lists all NI-DAQmx devices
    ↓
PXIeControlGUI.__init__()
    ↓
FrequencyManager loads frequencies.CSV
    ↓
MultiCardGenerator initializes 32 ChannelConfig objects
    ↓
GUI displays with 4 tabs (SV1-SV4)
```

### 2. Frequency Selection
```
User selects frequency from dropdown
    ↓
PXIeControlGUI.on_frequency_changed()
    ↓
FrequencyManager.calculate_sample_rate()
    ↓
Returns optimal sample rate (100+ samples/cycle)
    ↓
GUI updates sample rate display and quality indicator
```

### 3. Channel Configuration
```
User enables channels and sets amplitudes
    ↓
GUI callbacks update MultiCardGenerator
    ↓
ChannelConfig objects updated with:
    - enabled: True/False
    - amplitude_uv: Value in microvolts
    ↓
Changes stored in memory (thread-safe with Lock)
```

### 4. Generation Start
```
User clicks "Start Generation"
    ↓
MultiCardGenerator.start_generation()
    ↓
Starts background worker thread
    ↓
Worker groups enabled channels by card
    ↓
For each card with enabled channels:
    ↓
    Creates AO Task (analog output)
    ↓
    Adds AO channels (AO0, AO1)
    ↓
    Generates sine waveforms with individual amplitudes
    ↓
    Configures continuous output
    ↓
    Starts AO task
    ↓
    Creates AI Task (analog input)
    ↓
    Adds AI channels (AI0, AI1)
    ↓
    Sets large buffer (srate * 2 samples)
    ↓
    Starts AI task
    ↓
Background thread loops:
    - Reads AI data every 20ms (max(srate * 0.1, 5000) samples)
    - Calculates RMS and Peak for each channel
    - Updates GUI displays
    - Stores data in oscilloscope buffer (last 5000 samples)
    - Monitors for errors
```

### 5. Real-Time Monitoring
```
Background worker continuously reads AI channels:
    ↓
Every 20ms:
    Read analog input data
    ↓
    Calculate RMS voltage for each channel
    ↓
    Calculate Peak voltage for each channel
    ↓
    Update GUI labels (blue=RMS, green=Peak)
    ↓
    Store last 5000 samples in oscilloscope buffer
    ↓
    Check for buffer overflow warnings
```

### 6. Oscilloscope Window
```
User clicks "📊 Scope" button
    ↓
OscilloscopeWindow created
    ↓
Retrieves data from MultiCardGenerator.get_scope_data()
    ↓
matplotlib embedded in tkinter window
    ↓
Updates every 100ms:
    Get latest scope buffer data (copy)
    ↓
    Plot waveform
    ↓
    Check for clipping (>9.5V or <-9.5V)
    ↓
    Display warning if clipping detected
    ↓
    Show statistics (RMS, Peak, Frequency)
    ↓
User can:
    - Adjust time span (10ms to 200ms)
    - Change Y-scale (Auto, ±1V, ±2V, ±5V, ±10V)
    - Freeze display to examine waveform
    - Close window (does not affect generation)
```

### 7. Runtime Updates
```
User changes amplitude or enables/disables channel
    ↓
GUI callback updates ChannelConfig
    ↓
Background worker detects change (via Lock)
    ↓
Regenerates waveforms
    ↓
Updates DAQmx task
    ↓
Output continues seamlessly
```

### 8. Generation Stop
```
User clicks "Stop Generation"
    ↓
MultiCardGenerator.stop_generation()
    ↓
Sets stop_event
    ↓
Background thread exits
    ↓
Stops and closes all AO tasks
    ↓
Stops and closes all AI tasks
    ↓
GUI updates all channel statuses
    ↓
Oscilloscope windows continue showing last data
```

## Thread Architecture

```
Main Thread (GUI)
├── tkinter event loop
├── GUI updates (RMS/Peak displays)
├── User input handling
└── Oscilloscope windows (matplotlib plots)
    │
    └─[Lock]─► MultiCardGenerator configuration
                     │
                     ▼
              Background Worker Thread
              ├── Reads configuration (thread-safe)
              ├── Manages AO/AI DAQmx tasks
              ├── Generates waveforms
              ├── Reads analog input every 20ms
              ├── Calculates RMS/Peak values
              ├── Stores oscilloscope buffer data
              └── Continuous monitoring loop
```

## Data Classes

### FrequencyOption
```python
@dataclass
class FrequencyOption:
    frequency: float    # Hz
    name: str          # Display name
    available: bool    # Show in dropdown
    enabled: bool      # Alternative flag
```

### ChannelConfig
```python
@dataclass
class ChannelConfig:
    card_name: str         # "SV1", "SV2", "SV3", "SV4"
    channel_number: int    # 0-1 (AO0, AO1)
    amplitude_uv: float    # Microvolts
    enabled: bool          # Active/inactive
    input_rms: float       # Real-time RMS from AI
    input_peak: float      # Real-time Peak from AI
```

## File Dependencies

```
main.py
├── Import: nidaqmx (NI-DAQmx Python API)
├── Import: numpy (waveform generation & signal processing)
├── Import: matplotlib (oscilloscope display)
├── Import: tkinter (GUI)
├── Import: csv (frequency loading)
├── Import: threading (background worker)
└── Import: dataclasses (config objects)

Runtime Dependencies:
├── frequencies.CSV (loaded by FrequencyManager)
└── NI-DAQmx drivers (system level)
```

## Key Design Patterns

1. **Dataclass Pattern**: `FrequencyOption`, `ChannelConfig`
   - Immutable data structures
   - Type-safe configuration

2. **Manager Pattern**: `FrequencyManager`, `MultiCardGenerator`
   - Encapsulate complex logic
   - Clean API for GUI

3. **Observer Pattern**: GUI callbacks
   - Update generator on user input
   - Real-time status updates

4. **Producer-Consumer Pattern**: Background thread
   - GUI produces configuration
   - Worker consumes and generates output
   - Worker reads AI data and provides to GUI

5. **Resource Management**: Context managers
   - Proper task cleanup (AO and AI)
   - Exception-safe shutdown

6. **Buffering Pattern**: Oscilloscope data
   - Fixed-size ring buffer (5000 samples)
   - Thread-safe data access with copy()
   - Non-blocking updates with draw_idle()

## Scalability

Current: 4 cards × 2 channels = 8 analog outputs + 8 analog inputs

To add more cards:
1. Add names to `MultiCardGenerator.CARD_NAMES`
2. Configure devices in NI MAX
3. GUI automatically creates tabs

To change channels per card:
1. Update `MultiCardGenerator.CHANNELS_PER_CARD`
2. GUI automatically adjusts
3. AI channels mirror AO channels (AI0-AI1)

## Error Handling

```
Every layer has error handling:
├── GUI: User-friendly messageboxes
├── Generator: Graceful fallbacks
├── DAQmx: Try/except with cleanup
└── CSV: Fallback to defaults
```
