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
│  │  - Real-time status display                            │ │
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
│  │  - 32 total channels (8 per card)                     │ │
│  │  - Thread-safe configuration                           │ │
│  │  - Background output worker                            │ │
│  │                                                         │ │
│  │  ChannelConfig objects:                                │ │
│  │  [SV1/AO0-7] [SV2/AO0-7] [SV3/AO0-7] [SV4/AO0-7]    │ │
│  └───────────────────┬────────────────────────────────────┘ │
│                      │                                       │
│  ┌───────────────────▼────────────────────────────────────┐ │
│  │               NI-DAQmx Tasks                            │ │
│  │  - One task per active card                            │ │
│  │  - Continuous waveform generation                      │ │
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

## Data Flow

### 1. Startup
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
    Creates NI-DAQmx Task
    ↓
    Adds AO channels
    ↓
    Generates sine waveforms with individual amplitudes
    ↓
    Configures continuous output
    ↓
    Starts task
    ↓
Background thread loops, monitoring for changes
```

### 5. Runtime Updates
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

### 6. Generation Stop
```
User clicks "Stop Generation"
    ↓
MultiCardGenerator.stop_generation()
    ↓
Sets stop_event
    ↓
Background thread exits
    ↓
Stops and closes all DAQmx tasks
    ↓
GUI updates all channel statuses
```

## Thread Architecture

```
Main Thread (GUI)
├── tkinter event loop
├── GUI updates
└── User input handling
    │
    └─[Lock]─► MultiCardGenerator configuration
                     │
                     ▼
              Background Worker Thread
              ├── Reads configuration (thread-safe)
              ├── Manages DAQmx tasks
              ├── Generates waveforms
              └── Continuous output loop
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
    channel_number: int    # 0-7
    amplitude_uv: float    # Microvolts
    enabled: bool          # Active/inactive
```

## File Dependencies

```
main.py
├── Import: nidaqmx (NI-DAQmx Python API)
├── Import: numpy (waveform generation)
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

5. **Resource Management**: Context managers
   - Proper task cleanup
   - Exception-safe shutdown

## Scalability

Current: 4 cards × 8 channels = 32 channels

To add more cards:
1. Add names to `MultiCardGenerator.CARD_NAMES`
2. Configure devices in NI MAX
3. GUI automatically creates tabs

To change channels per card:
1. Update `MultiCardGenerator.CHANNELS_PER_CARD`
2. GUI automatically adjusts

## Error Handling

```
Every layer has error handling:
├── GUI: User-friendly messageboxes
├── Generator: Graceful fallbacks
├── DAQmx: Try/except with cleanup
└── CSV: Fallback to defaults
```
