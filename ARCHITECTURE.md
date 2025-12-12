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

## Advanced Features: Dual-Frequency Generation

### Concept

The system can be extended to generate combined signals by mathematically summing multiple sine waves before output. This is useful for direction-finding equipment and other applications requiring composite signals.

### Use Case: Direction-Finding Equipment

Direction-finding systems often use phase relationships between two frequencies to determine transmitter bearing. A common approach:

- **Primary frequency**: Base signal (e.g., 1 kHz)
- **Secondary frequency**: Half the primary (e.g., 500 Hz)
- **Combined output**: Sum of both signals
- **Phase relationship**: Allows receiver to determine direction

### Implementation Approach

```python
def _generate_dual_frequency_waveform(self, frequency1, frequency2, 
                                      amplitude1, amplitude2, 
                                      sample_rate, num_samples):
    """
    Generate combined dual-frequency waveform.
    
    Args:
        frequency1: Primary frequency in Hz (e.g., 1000)
        frequency2: Secondary frequency in Hz (e.g., 500)
        amplitude1: Primary amplitude in volts
        amplitude2: Secondary amplitude in volts
        sample_rate: DAC sample rate in Hz
        num_samples: Number of samples to generate
    
    Returns:
        numpy array of combined waveform
    """
    duration = num_samples / sample_rate
    t = np.linspace(0, duration, num_samples, endpoint=False)
    
    # Generate both sine waves
    primary = amplitude1 * np.sin(2 * np.pi * frequency1 * t)
    secondary = amplitude2 * np.sin(2 * np.pi * frequency2 * t)
    
    # Combine signals
    combined = primary + secondary
    
    # Prevent clipping - scale if exceeds ±10V
    max_voltage = np.max(np.abs(combined))
    if max_voltage > 10.0:
        scale_factor = (10.0 / max_voltage) * 0.95  # 95% to leave headroom
        combined = combined * scale_factor
        print(f"Warning: Signal scaled by {scale_factor:.3f} to prevent clipping")
    
    return combined
```

### Example: 1 kHz + 500 Hz Direction-Finding Signal

```python
# Configuration
primary_freq = 1000      # 1 kHz primary
secondary_freq = 500     # 500 Hz secondary (2:1 ratio)
primary_amplitude = 4.0  # 4V peak
secondary_amplitude = 3.0 # 3V peak
sample_rate = 100000     # 100 kHz (100 samples/cycle for 1 kHz)

# Generate combined signal
combined_signal = _generate_dual_frequency_waveform(
    frequency1=primary_freq,
    frequency2=secondary_freq,
    amplitude1=primary_amplitude,
    amplitude2=secondary_amplitude,
    sample_rate=sample_rate,
    num_samples=10000
)

# Result: 7V peak (4V + 3V), well within ±10V limits
```

### Key Considerations

#### 1. Sample Rate Selection
- Must satisfy Nyquist for **both** frequencies
- Current system uses 100+ samples/cycle
- For 1 kHz primary: 100 kHz+ sample rate recommended
- For higher frequencies: use 2 MHz max (PXIe-4468 limit)

#### 2. Amplitude Management
- Combined peak = amplitude1 + amplitude2 (worst case)
- Must not exceed ±10V hardware limit
- Automatic scaling prevents clipping
- Monitor with oscilloscope feature to verify

#### 3. Phase Coherence
- Both signals generated from same time array
- Ensures consistent phase relationship
- Critical for direction-finding accuracy
- Regenerated together maintains coherence

#### 4. Frequency Relationships
- Common ratios: 2:1, 3:1, 4:1
- Example: 1000 Hz + 500 Hz (2:1)
- Example: 1500 Hz + 500 Hz (3:1)
- Any mathematical relationship possible

### Integration with Current System

To add dual-frequency support, modify `MultiCardGenerator._generate_waveforms()`:

**Current behavior** (single frequency):
```python
# Around line 465-490 in main.py
sine_wave = np.sin(2 * np.pi * self.frequency * t)
channel_samples[ch] = sine_wave * amplitude_v
```

**Enhanced for dual-frequency**:
```python
# Option 1: Per-channel dual-frequency configuration
sine_wave1 = np.sin(2 * np.pi * self.frequency * t)
sine_wave2 = np.sin(2 * np.pi * self.frequency2 * t)  # New parameter
combined = sine_wave1 + (sine_wave2 * self.freq2_ratio)  # Adjustable mix
channel_samples[ch] = combined * amplitude_v

# Option 2: Global dual-frequency mode
if self.dual_freq_enabled:
    primary = np.sin(2 * np.pi * self.frequency * t)
    secondary = np.sin(2 * np.pi * (self.frequency / 2) * t)  # Half frequency
    combined = (primary * self.primary_mix) + (secondary * self.secondary_mix)
    channel_samples[ch] = combined * amplitude_v
```

### Benefits for RF Testing

1. **Direction calibration**: Test bearing accuracy
2. **Multi-tone response**: Verify amplifier linearity
3. **Intermodulation testing**: Check for distortion products
4. **Beat frequency generation**: Low-frequency envelope for testing
5. **Complex signal scenarios**: Real-world signal simulation

### Future Enhancement Ideas

- GUI option to enable dual-frequency mode
- Adjustable frequency ratio (1:2, 1:3, etc.)
- Independent amplitude control for each frequency
- Phase offset control
- Three or more frequency combinations
- Arbitrary waveform selection (sine, square, triangle)
- CSV-based frequency pair definitions
