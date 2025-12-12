# PXIe-4468 Multi-Card Sine Wave Generator

Professional Python application for controlling up to four PXIe-4468 data acquisition cards (SV1-SV4) with per-channel amplitude control in microvolts.

## Features

### Multi-Card Support
- **4 Cards**: Control up to 4 PXIe-4468 cards simultaneously (SV1, SV2, SV3, SV4)
- **8 Channels Total**: Each card provides 2 analog output channels (AO0-AO1)
- **Independent Control**: Each channel can be individually enabled/disabled and configured
- **Mirrored Inputs**: AI0-AI1 monitor the AO0-AO1 outputs for RF amplifier response

### Frequency Management
- **CSV-Based Frequencies**: Load available frequencies from `frequencies.CSV`
- **Auto Sample Rate**: Automatically calculates optimal sample rate based on selected frequency
  - Ensures at least 100 samples per cycle for high-quality waveforms
  - Uses common sample rates (1kHz to 2MHz)
- **Quality Indicator**: Real-time quality assessment (Excellent/Good/Fair/Poor)

### Amplitude Control
- **Microvolt Precision**: Set amplitude for each channel in microvolts (µV)
- **Bulk Operations**: Set all channels on a card to the same amplitude
- **Real-Time Display**: Status shows current amplitude in µV or mV

### Real-Time Input Monitoring
- **RMS Voltage**: Continuous RMS measurement for each analog input
- **Peak Voltage**: Real-time peak voltage detection
- **Live Updates**: Measurements update 10 times per second
- **RF Amplifier Testing**: Monitor amplifier response to stimulus signals

### Oscilloscope Display
- **📊 Scope Button**: Open oscilloscope window for any channel
- **Live Waveforms**: Real-time visualization of analog input signals
- **Clipping Detection**: Automatic warnings when signal approaches ±10V limits
- **Adjustable Controls**: Configurable Y-scale (Auto, ±1V to ±10V) and time span (10ms to 200ms)
- **Freeze Function**: Pause display to examine waveform details
- **Signal Statistics**: RMS, peak, and frequency information

### Professional GUI
- **Tabbed Interface**: Separate tab for each card
- **Live Status**: Real-time status for each channel (Idle/Ready/Active/Disabled)
- **Easy Control**: Enable/disable channels with checkboxes
- **Frequency Selector**: Dropdown menu with all available frequencies from CSV
- **Start/Stop**: Simple buttons to control signal generation
- **Inline Measurements**: RMS and peak values displayed next to each channel

## Setup

### Prerequisites
1. **Python 3.8+** installed
2. **NI-DAQmx drivers** installed from National Instruments
3. **PXIe chassis** connected via Thunderbolt
4. **Device Configuration**: Cards must be named SV1, SV2, SV3, SV4 in NI MAX

### Installation

1. Clone or download this repository

2. Create and activate virtual environment:
   ```cmd
   python -m venv venv
   venv\Scripts\activate.bat
   ```

3. Install dependencies:
   ```cmd
   pip install -r requirements.txt
   ```

### Device Configuration (NI MAX)
Before running the application, ensure your PXIe-4468 cards are properly configured in NI Measurement & Automation Explorer (NI MAX):

1. Open NI MAX
2. Expand "Devices and Interfaces"
3. Find your PXIe-4468 cards
4. Rename them to: **SV1**, **SV2**, **SV3**, **SV4**

## Usage

### Running the Application

```cmd
python main.py
```

### Using the GUI

1. **Select Frequency**
   - Choose from the dropdown list (loaded from `frequencies.CSV`)
   - Sample rate automatically adjusts for optimal quality
   - Quality indicator shows signal quality

2. **Configure Channels**
   - Click on a card tab (SV1, SV2, SV3, SV4)
   - Check/uncheck boxes to enable/disable channels (AO0, AO1)
   - Enter amplitude in microvolts (µV) for each channel
   - Use "Enable All" / "Disable All" for quick setup
   - Use "Set All Amplitudes" to apply same amplitude to all channels

3. **Start Generation**
   - Click "▶ Start Generation"
   - All enabled channels will output sine waves at the selected frequency
   - Status bar shows active generation details
   - RMS and Peak columns show live input measurements

4. **Monitor RF Amplifier Response**
   - Watch the Input RMS and Peak columns update in real-time
   - Values shown are from AI0-AI1 monitoring your RF amplifier outputs
   - Blue text = RMS voltage, Green text = Peak voltage

5. **View Waveforms (Oscilloscope)**
   - Click "📊 Scope" button next to any channel
   - View real-time waveform from the analog input
   - Check for clipping warnings (red alerts)
   - Adjust time span (10ms to 200ms)
   - Change Y-scale (Auto or fixed ranges)
   - Click "Freeze" to pause and examine the waveform
   - Open multiple oscilloscope windows simultaneously

6. **Stop Generation**
   - Click "⏹ Stop Generation"
   - All outputs stop immediately

### Frequency CSV Format

The `frequencies.CSV` file contains available frequencies. Format:
```csv
Frequency,Name,Available,Enabled,...
50,50Hz,X,X,...
60,60Hz,X,X,...
1000,1kHz,,,
```

- **Frequency**: Value in Hz
- **Name**: Display name
- **Available/Enabled**: "X" marks frequency as selectable

## Technical Details

### Sample Rate Calculation
The application automatically calculates the optimal sample rate:
- Minimum: 100 samples per cycle (for high quality)
- Rounds to standard rates: 1kHz, 2.5kHz, 5kHz, 10kHz, 25kHz, 50kHz, 100kHz, 200kHz, 500kHz, 1MHz, 2MHz
- Maximum: 2 MS/s (PXIe-4468 limit)

### Amplitude Range
- **Input**: Microvolts (µV)
- **Range**: 0 to 10,000,000 µV (0 to 10V)
- **Conversion**: Automatically converts µV to V for DAQmx
- **Precision**: Floating-point precision maintained

### Multi-Channel Output & Input
- All channels on a card share the same frequency and sample rate
- Each channel has independent amplitude
- Waveforms are generated and written as interleaved multi-channel data
- Continuous regeneration mode for seamless output
- Analog inputs (AI0-AI1) monitor corresponding outputs (AO0-AO1)
- Large input buffers (2 seconds) prevent data loss
- Fast acquisition rate (50 reads/second) ensures real-time monitoring

## Requirements

- **Python**: 3.8 or higher
- **NI-DAQmx**: Compatible version installed
- **Hardware**: PXIe chassis with PXIe-4468 cards
- **Connection**: Thunderbolt connection to chassis

## Dependencies

```
nidaqmx      # NI-DAQmx Python API
numpy        # Numerical computing
matplotlib   # Oscilloscope display
tkinter      # GUI (included with Python)
```

## Troubleshooting

### "No devices found"
- Ensure PXIe chassis is powered on
- Check Thunderbolt connection
- Verify NI-DAQmx drivers are installed
- Run NI MAX to confirm devices are detected

### "No channels enabled"
- Enable at least one channel on any card
- Check the checkbox next to desired channels
- Click "Start Generation" again

### Sample Rate Too Low
- The application automatically optimizes sample rate
- If quality shows "Poor", select a lower frequency
- Or the frequency may be too high for the hardware

### Device Names Not Found
- Configure device names in NI MAX
- Rename devices to SV1, SV2, SV3, SV4
- Restart the application

### Input Measurements Show Zero
- Ensure analog inputs (AI0, AI1) are connected
- Check that RF amplifier outputs are connected to AI channels
- Verify generation is running (not just started)

### Oscilloscope Shows No Waveform
- Make sure generation is active before opening oscilloscope
- Check that the channel is enabled
- Verify analog input connections
- Wait a moment for buffer to fill with data

### "Application is not able to keep up" Error
- This has been fixed with larger buffers and faster reads
- If still occurring, reduce the number of enabled channels
- Close unnecessary oscilloscope windows

## Project Structure

```
PXIe-4468_Python/
├── main.py                    # Main application with GUI
├── frequencies.CSV            # Available frequencies
├── requirements.txt           # Python dependencies
├── README.md                  # This file
└── labview/                   # LabVIEW reference materials
    ├── example_python/
    └── ...
```

## License

This project is for controlling National Instruments PXIe-4468 hardware.
