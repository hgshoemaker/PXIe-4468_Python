# Quick Start Guide - PXIe-4468 Multi-Card Generator

## Setup Checklist

- [ ] Python 3.8+ installed
- [ ] NI-DAQmx drivers installed
- [ ] PXIe chassis connected via Thunderbolt
- [ ] Virtual environment created
- [ ] Dependencies installed
- [ ] Devices named SV1-SV4 in NI MAX

## Quick Commands

### Create venv and Install Dependencies
```cmd
cd C:\Users\hgsho\source\repos\PXIe-4468_Python
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

### Run Application
```cmd
venv\Scripts\activate.bat
python main.py
```

## GUI Overview

### Top Control Panel
- **Frequency Dropdown**: Select from frequencies in CSV
- **Sample Rate**: Auto-calculated, displayed next to frequency
- **Quality Indicator**: Shows Excellent/Good/Fair/Poor
- **Start/Stop Buttons**: Control signal generation

### Card Tabs (SV1, SV2, SV3, SV4)
Each tab has:
- **Enable All / Disable All**: Quick channel control
- **Set All Amplitudes**: Apply same amplitude to all 8 channels
- **8 Channel Rows** (AO0-AO7):
  - Checkbox: Enable/disable channel
  - Amplitude field: Enter value in µV
  - Status: Shows current state

## Common Workflows

### 1. Output Same Frequency, Different Amplitudes
1. Select frequency from dropdown
2. Go to card tab (e.g., SV1)
3. Enable desired channels
4. Set individual amplitudes for each channel
5. Click "Start Generation"

### 2. Use All Cards at Once
1. Select frequency
2. Visit each card tab (SV1, SV2, SV3, SV4)
3. Enable channels on each card
4. Set amplitudes
5. Click "Start Generation" (works across all cards)

### 3. Quick Test Single Channel
1. Select 1000 Hz (or any frequency)
2. Go to SV1 tab
3. Enable only AO0
4. Set amplitude to 1000000 µV (1 mV)
5. Click "Start Generation"

## Amplitude Examples

| µV Value | Equivalent | Use Case |
|----------|-----------|----------|
| 100 | 0.1 mV | Low-level signal |
| 1000 | 1 mV | Standard test |
| 10000 | 10 mV | Medium signal |
| 100000 | 0.1 V | High signal |
| 1000000 | 1 V | Full volt |
| 10000000 | 10 V | Maximum |

## Frequency CSV Tips

The application reads `frequencies.CSV` with this structure:
```csv
Frequency,Name,Available,Enabled,...
50,50Hz,X,X,...
```

- Put "X" in Available or Enabled column to show frequency in dropdown
- Frequency must be numeric (Hz)
- Name can be any label

## Troubleshooting

| Issue | Solution |
|-------|----------|
| GUI doesn't open | Check Python/tkinter installation |
| "No devices" error | Verify Thunderbolt connection, check NI MAX |
| Can't find SV1 | Rename devices in NI MAX to SV1, SV2, SV3, SV4 |
| No frequencies in dropdown | Check frequencies.CSV exists and has correct format |
| Poor quality warning | Lower frequency or increase sample rate |

## Key Features

✅ **Multi-card support**: Control 4 cards simultaneously  
✅ **Per-channel amplitude**: Independent control in µV  
✅ **Auto sample rate**: Automatically optimized  
✅ **CSV frequencies**: Easy to customize  
✅ **Professional GUI**: Tabbed interface with real-time status  
✅ **Bulk operations**: Set all channels at once  

## Next Steps

1. Run `python main.py` to test the GUI
2. Check device connections in NI MAX
3. Customize `frequencies.CSV` for your needs
4. Configure channel amplitudes for your test setup
