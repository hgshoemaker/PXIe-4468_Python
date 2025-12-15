"""
Multi-Card PXIe-4468 Sine Wave Generator
Supports 4 cards (SV1-SV4) with per-channel amplitude control in microvolts.
"""

import nidaqmx
import nidaqmx.system
import numpy as np
import time
import csv
import tkinter as tk
from tkinter import ttk, messagebox
from threading import Thread, Event, Lock
from dataclasses import dataclass
from typing import List, Dict, Optional
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


@dataclass
class FrequencyOption:
    """Represents a frequency option from the CSV file."""
    frequency: float
    name: str
    available: bool = False
    enabled: bool = False


@dataclass
class ChannelConfig:
    """Configuration for a single output channel."""
    card_name: str
    channel_number: int  # 0-7 for PXIe-4468
    amplitude_uv: float = 1000.0  # microvolts
    enabled: bool = True


class FrequencyManager:
    """Manages loading and selection of frequencies from CSV."""
    
    def __init__(self, csv_path: str = "frequencies.CSV"):
        self.csv_path = csv_path
        self.frequencies: List[FrequencyOption] = []
        self.load_frequencies()
    
    def load_frequencies(self):
        """Load frequencies from CSV file."""
        try:
            with open(self.csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        freq = float(row['Frequency'])
                        name = row.get('Name', f"{freq} Hz")
                        available = row.get('Available', '').strip().upper() == 'X'
                        enabled = row.get('Enabled', '').strip().upper() == 'X'
                        
                        self.frequencies.append(FrequencyOption(
                            frequency=freq,
                            name=name,
                            available=available,
                            enabled=enabled
                        ))
                    except (ValueError, KeyError):
                        continue
        except Exception as e:
            print(f"Error loading frequencies from {self.csv_path}: {e}")
            # Fallback to default frequencies
            self.frequencies = [
                FrequencyOption(50, "50Hz", True, True),
                FrequencyOption(60, "60Hz", True, True),
                FrequencyOption(100, "100Hz", True, True),
                FrequencyOption(1000, "1kHz", True, True),
                FrequencyOption(10000, "10kHz", True, True),
            ]
    
    def get_available_frequencies(self) -> List[FrequencyOption]:
        """Get list of available frequencies."""
        return [f for f in self.frequencies if f.available or f.enabled]
    
    def calculate_sample_rate(self, frequency: float) -> int:
        """
        Calculate optimal sample rate for a given frequency.
        Ensures at least 100 samples per cycle, rounds to nice values.
        PXIe-4468 AO maximum: 200 kS/s, AI maximum: 250 kS/s
        """
        # Hardware limit for PXIe-4468 analog outputs
        MAX_SAMPLE_RATE = 200000  # 200 kS/s for AO
        
        # Aim for at least 100 samples per cycle for good quality
        min_samples_per_cycle = 100
        base_rate = frequency * min_samples_per_cycle
        
        # If requested rate exceeds hardware limit, use maximum
        if base_rate > MAX_SAMPLE_RATE:
            return MAX_SAMPLE_RATE
        
        # Round to common sample rates (must not exceed MAX_SAMPLE_RATE)
        common_rates = [1000, 2500, 5000, 10000, 25000, 50000, 100000, 200000]
        
        for rate in common_rates:
            if rate >= base_rate:
                return rate
        
        # Fallback to maximum
        return MAX_SAMPLE_RATE


class MultiCardGenerator:
    """Manages sine wave generation across multiple PXIe-4468 cards."""
    
    CHANNELS_PER_CARD = 2  # PXIe-4468 has 2 analog outputs: ao0, ao1
    CARD_NAMES = ["SV1", "SV2", "SV3", "SV4"]
    MAX_AO_SAMPLE_RATE = 200000  # AO (output) limit: 200 kS/s
    MAX_AI_SAMPLE_RATE = 250000  # AI (input) limit: 250 kS/s
    
    def __init__(self):
        self.ao_tasks: Dict[str, nidaqmx.Task] = {}  # Analog output tasks
        self.ai_tasks: Dict[str, nidaqmx.Task] = {}  # Analog input tasks
        self.lock = Lock()
        self.running = False
        self.stop_event = Event()
        
        # Current configuration
        self.frequency = 1000.0  # Hz
        self.sample_rate = 100000  # Hz (for AO output)
        self.ai_sample_rate = self.MAX_AI_SAMPLE_RATE  # Always use max for AI (oscilloscope: 250kS/s)
        self.channels: List[ChannelConfig] = []
        
        # Input data storage (RMS and peak per channel)
        self.input_data: Dict[str, Dict[str, float]] = {}  # {"SV1_0": {"rms": 0.0, "peak": 0.0}}
        
        # Oscilloscope waveform buffer (stores last N samples for each channel)
        self.scope_buffer_size = 5000  # Number of samples to store
        self.scope_data: Dict[str, np.ndarray] = {}  # {"SV1_0": array of samples}
        
        # Initialize all channels for all cards (disabled by default)
        for card_name in self.CARD_NAMES:
            for ch in range(self.CHANNELS_PER_CARD):
                self.channels.append(ChannelConfig(
                    card_name=card_name,
                    channel_number=ch,
                    amplitude_uv=1000.0,
                    enabled=False
                ))
        
        self.output_thread = None
    
    def get_channel(self, card_name: str, channel_number: int) -> Optional[ChannelConfig]:
        """Get configuration for a specific channel."""
        for ch in self.channels:
            if ch.card_name == card_name and ch.channel_number == channel_number:
                return ch
        return None
    
    def set_frequency(self, frequency: float, sample_rate: int):
        """Set the output frequency and sample rate for all channels."""
        with self.lock:
            self.frequency = frequency
            self.sample_rate = sample_rate
    
    def set_channel_amplitude(self, card_name: str, channel_number: int, amplitude_uv: float):
        """Set amplitude for a specific channel in microvolts."""
        channel = self.get_channel(card_name, channel_number)
        if channel:
            with self.lock:
                channel.amplitude_uv = amplitude_uv
    
    def set_channel_enabled(self, card_name: str, channel_number: int, enabled: bool):
        """Enable or disable a specific channel."""
        channel = self.get_channel(card_name, channel_number)
        if channel:
            with self.lock:
                channel.enabled = enabled
    
    def generate_sinewave(self, frequency: float, amplitude_v: float, sample_rate: int) -> np.ndarray:
        """Generate one period of a sine wave."""
        period = 1.0 / frequency
        num_samples = int(sample_rate * period)
        # Ensure at least 2 samples
        if num_samples < 2:
            num_samples = 2
        t = np.linspace(0, period, num_samples, endpoint=False)
        return amplitude_v * np.sin(2 * np.pi * frequency * t)
    
    def start_generation(self) -> str:
        """Start continuous sine wave generation. Returns status message."""
        print("\n" + "="*60)
        print("START GENERATION CALLED")
        print("="*60)
        
        if self.running:
            print("Generator already running")
            return "Generator already running"
        
        # Check if any channels are enabled
        enabled_channels = [ch for ch in self.channels if ch.enabled]
        print(f"Enabled channels: {len(enabled_channels)}")
        
        if not enabled_channels:
            print("ERROR: No channels enabled!")
            return "No channels enabled. Please enable at least one channel."
        
        # Show which channels are enabled
        for ch in enabled_channels:
            print(f"  - {ch.card_name}/AO{ch.channel_number}: {ch.amplitude_uv} µV")
        
        print(f"Frequency: {self.frequency} Hz")
        print(f"Sample Rate: {self.sample_rate} Hz")
        
        self.stop_event.clear()
        self.running = True
        self.output_thread = Thread(target=self._output_worker, daemon=True)
        self.output_thread.start()
        
        print(f"Background thread started")
        print("="*60)
        
        return f"Started generation on {len(enabled_channels)} channel(s)"
    
    def stop_generation(self):
        """Stop all sine wave generation."""
        if not self.running:
            return
        
        self.stop_event.set()
        self.running = False
        
        # Wait for thread to finish
        if self.output_thread:
            self.output_thread.join(timeout=2.0)
        
        # Close all AO tasks
        for task_name, task in list(self.ao_tasks.items()):
            try:
                task.stop()
                task.close()
            except:
                pass
        self.ao_tasks.clear()
        
        # Close all AI tasks
        for task_name, task in list(self.ai_tasks.items()):
            try:
                task.stop()
                task.close()
            except:
                pass
        self.ai_tasks.clear()
    
    def _output_worker(self):
        """Background thread that manages continuous output."""
        print("\n*** OUTPUT WORKER THREAD STARTED ***")
        tasks_created = False
        try:
            # Initial task creation
            with self.lock:
                freq = self.frequency
                srate = self.sample_rate  # AO sample rate
                ai_srate = self.ai_sample_rate  # AI sample rate (always max)
                # Create copy of enabled channels
                enabled_chs = [(ch.card_name, ch.channel_number, ch.amplitude_uv) 
                              for ch in self.channels if ch.enabled]
            
            print(f"Initial setup: {len(enabled_chs)} enabled channels")
            
            # Group channels by card
            cards = {}
            for card_name, ch_num, amp_uv in enabled_chs:
                if card_name not in cards:
                    cards[card_name] = []
                cards[card_name].append((ch_num, amp_uv))
            
            print(f"Cards to configure: {list(cards.keys())}")
            
            # Create tasks for each card
            for card_name, channel_list in cards.items():
                task_name = card_name
                
                print(f"\nCreating task for {card_name}...")
                try:
                    task = nidaqmx.Task()
                    print(f"  Task object created")
                    
                    # Sort channels by channel number to ensure consistent ordering
                    sorted_channels = sorted(channel_list, key=lambda x: x[0])
                    
                    # Add all channels for this card in sorted order
                    for ch_num, amp_uv in sorted_channels:
                        channel_name = f"{card_name}/ao{ch_num}"
                        print(f"  Adding channel: {channel_name} ({amp_uv} µV)")
                        task.ao_channels.add_ao_voltage_chan(
                            channel_name,
                            min_val=-10.0,
                            max_val=10.0
                        )
                    
                    # Configure timing
                    period = 1.0 / freq
                    samples = self.generate_sinewave(freq, 1.0, srate)  # 1V reference
                    print(f"  Samples per period: {len(samples)}")
                    
                    task.timing.cfg_samp_clk_timing(
                        rate=srate,
                        sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS,
                        samps_per_chan=len(samples)
                    )
                    print(f"  Timing configured: {srate} Hz")
                    
                    task.out_stream.regen_mode = nidaqmx.constants.RegenerationMode.ALLOW_REGENERATION
                    
                    # Generate waveforms for each channel with individual amplitudes
                    # Use the same sorted order as when adding channels
                    waveforms = []
                    for ch_num, amp_uv in sorted_channels:
                        amp_v = amp_uv / 1e6  # Convert microvolts to volts
                        waveform = self.generate_sinewave(freq, amp_v, srate)
                        waveforms.append(waveform)
                        # Debug: show waveform stats
                        wf_min, wf_max = waveform.min(), waveform.max()
                        wf_rms = np.sqrt(np.mean(waveform**2))
                        print(f"  Generated waveform for AO{ch_num}: {amp_v:.6f} V ({amp_uv:.0f} µV)")
                        print(f"    Waveform stats - Min: {wf_min:.6f}V, Max: {wf_max:.6f}V, RMS: {wf_rms:.6f}V, Samples: {len(waveform)}")
                    
                    # Write data
                    # For multiple channels, nidaqmx expects a 2D array where each row is a channel
                    # Convert list of waveforms to numpy array
                    if len(waveforms) == 1:
                        # Single channel - write 1D array
                        write_data = waveforms[0]
                        print(f"  Writing single channel waveform ({len(write_data)} samples)...")
                    else:
                        # Multiple channels - write 2D array (channels x samples)
                        write_data = np.array(waveforms)
                        print(f"  Writing {len(waveforms)} channel waveforms (shape: {write_data.shape})...")
                    
                    task.write(write_data, auto_start=False)
                    print(f"  Starting task...")
                    task.start()
                    
                    self.ao_tasks[task_name] = task
                    tasks_created = True
                    print(f"  ✓ Task started successfully for {card_name}")
                    
                except Exception as e:
                    print(f"  ✗ ERROR creating task for {card_name}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Create analog input tasks to monitor outputs (optional - don't fail if this doesn't work)
            if tasks_created:
                print("\n--- Creating Analog Input Monitoring (Optional) ---")
                for card_name, channel_list in cards.items():
                    try:
                        ai_task = nidaqmx.Task()
                        print(f"Creating AI task for {card_name}...")
                        
                        # Add AI channels matching the AO channels
                        for ch_num, _ in channel_list:
                            channel_name = f"{card_name}/ai{ch_num}"
                            print(f"  Adding AI channel: {channel_name}")
                            ai_task.ai_channels.add_ai_voltage_chan(
                                channel_name,
                                terminal_config=nidaqmx.constants.TerminalConfiguration.PSEUDO_DIFF,
                                min_val=-10.0,
                                max_val=10.0
                            )
                        
                        # Configure timing for continuous acquisition with large buffer
                        # Use maximum sample rate for AI to get best oscilloscope display resolution
                        # Buffer size should be at least 2 seconds of data
                        buffer_size = int(ai_srate * 2)  # 2 seconds of buffer
                        ai_task.timing.cfg_samp_clk_timing(
                            rate=ai_srate,
                            sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS,
                            samps_per_chan=buffer_size
                        )
                        
                        # Configure input buffer to be even larger
                        ai_task.in_stream.input_buf_size = buffer_size * 2
                        
                        ai_task.start()
                        self.ai_tasks[card_name] = ai_task
                        print(f"  ✓ AI task started for {card_name}")
                        
                    except Exception as e:
                        print(f"  ⚠ Could not create AI task for {card_name}: {e}")
                        print(f"     Continuing without input monitoring for this card...")
                        # Continue - AI monitoring is optional
                        # Continue without AI monitoring
            
            if tasks_created:
                print("\n✓ ALL TASKS CREATED - Generation running continuously")
                print("  (Monitoring inputs and waiting for stop signal...)")
            
            # Keep thread alive and update input measurements
            while not self.stop_event.is_set():
                try:
                    # Read and process input data
                    for card_name, ai_task in list(self.ai_tasks.items()):
                        try:
                            # Read more samples to prevent buffer overflow
                            # Read at least 0.1 seconds worth of data
                            samples_to_read = max(int(srate * 0.1), 5000)
                            data = ai_task.read(number_of_samples_per_channel=samples_to_read, timeout=2.0)
                            
                            # Process each channel
                            if isinstance(data[0], list):
                                # Multiple channels
                                for ch_idx, channel_data in enumerate(data):
                                    channel_data = np.array(channel_data)
                                    rms = np.sqrt(np.mean(channel_data**2))
                                    peak = np.max(np.abs(channel_data))
                                    
                                    key = f"{card_name}_{ch_idx}"
                                    with self.lock:
                                        self.input_data[key] = {"rms": rms, "peak": peak}
                                        # Store waveform for oscilloscope
                                        if key not in self.scope_data:
                                            self.scope_data[key] = channel_data[:self.scope_buffer_size]
                                        else:
                                            # Roll buffer and append new data
                                            current = self.scope_data[key]
                                            new_data = np.concatenate([current, channel_data])
                                            self.scope_data[key] = new_data[-self.scope_buffer_size:]
                            else:
                                # Single channel
                                channel_data = np.array(data)
                                rms = np.sqrt(np.mean(channel_data**2))
                                peak = np.max(np.abs(channel_data))
                                
                                key = f"{card_name}_0"
                                with self.lock:
                                    self.input_data[key] = {"rms": rms, "peak": peak}
                                    # Store waveform for oscilloscope
                                    if key not in self.scope_data:
                                        self.scope_data[key] = channel_data[:self.scope_buffer_size]
                                    else:
                                        # Roll buffer and append new data
                                        current = self.scope_data[key]
                                        new_data = np.concatenate([current, channel_data])
                                        self.scope_data[key] = new_data[-self.scope_buffer_size:]
                        except Exception as e:
                            # Log AI read errors but continue
                            if "timeout" not in str(e).lower():
                                print(f"  AI read error for {card_name}: {e}")
                    
                    # Verify AO tasks are still running (every 20 iterations = ~1 second)
                    if not hasattr(self, '_check_counter'):
                        self._check_counter = 0
                    self._check_counter += 1
                    
                    if self._check_counter >= 20:
                        self._check_counter = 0
                        for card_name, ao_task in list(self.ao_tasks.items()):
                            try:
                                # Check if task is still running
                                if not ao_task.is_task_done():
                                    pass  # Task is running fine
                                else:
                                    print(f"  WARNING: AO task for {card_name} has stopped!")
                            except:
                                pass
                    
                    # Sleep less to read more frequently and prevent buffer overflow
                    time.sleep(0.02)  # Read every 20ms instead of 50ms
                    
                except Exception as e:
                    print(f"  Error in monitoring loop: {e}")
                    import traceback
                    traceback.print_exc()
                    time.sleep(0.1)
            
            print("\n*** STOPPING OUTPUT ***")
        
        except Exception as e:
            print(f"Output worker error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Clean up
            print("Cleaning up tasks...")
            for task in list(self.ao_tasks.values()):
                try:
                    task.stop()
                    task.close()
                except:
                    pass
            self.ao_tasks.clear()
            
            for task in list(self.ai_tasks.values()):
                try:
                    task.stop()
                    task.close()
                except:
                    pass
            self.ai_tasks.clear()
            print("*** OUTPUT WORKER THREAD ENDED ***")


    def get_input_measurements(self, card_name: str, channel_number: int) -> Dict[str, float]:
        """Get RMS and peak measurements for a specific input channel."""
        key = f"{card_name}_{channel_number}"
        with self.lock:
            return self.input_data.get(key, {"rms": 0.0, "peak": 0.0}).copy()
    
    def get_scope_data(self, card_name: str, channel_number: int) -> np.ndarray:
        """Get oscilloscope waveform data for a specific input channel. Returns a copy."""
        key = f"{card_name}_{channel_number}"
        with self.lock:
            data = self.scope_data.get(key, np.array([]))
            # Return a copy so we don't hold the lock during plotting
            return data.copy() if len(data) > 0 else np.array([])


class OscilloscopeWindow:
    """Oscilloscope display window for viewing real-time waveforms."""
    
    def __init__(self, parent, generator: MultiCardGenerator, card_name: str, channel_number: int):
        self.generator = generator
        self.card_name = card_name
        self.channel_number = channel_number
        self.window = tk.Toplevel(parent)
        self.window.title(f"Oscilloscope - {card_name}/AI{channel_number}")
        self.window.geometry("550x400")
        
        self.is_running = True
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Create matplotlib figure
        self.fig = Figure(figsize=(5.5, 3.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel('Time (ms)')
        self.ax.set_ylabel('Voltage (V)')
        self.ax.set_title(f'Input Waveform - {card_name}/AI{channel_number}')
        self.ax.grid(True, alpha=0.3)
        
        # Initialize line
        self.line, = self.ax.plot([], [], 'b-', linewidth=1)
        
        # Clipping indicator
        self.clip_text = self.ax.text(0.02, 0.98, '', transform=self.ax.transAxes,
                                      verticalalignment='top', fontsize=10, color='red',
                                      fontweight='bold',
                                      bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.8))
        
        # Stats text
        self.stats_text = self.ax.text(0.98, 0.98, '', transform=self.ax.transAxes,
                                       verticalalignment='top', horizontalalignment='right',
                                       fontsize=9,
                                       bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.7))
        
        # Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, self.window)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Controls frame
        controls = ttk.Frame(self.window)
        controls.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
        
        ttk.Label(controls, text="Y-Scale:").pack(side=tk.LEFT, padx=5)
        self.yscale_var = tk.StringVar(value="±100µV")
        yscale_combo = ttk.Combobox(controls, textvariable=self.yscale_var, width=12, 
                                    values=["Auto", "±100µV", "±200µV", "±300µV", "±500µV", "±1mV", "±10mV", "±100mV", "±1V", "±2V", "±5V", "±10V"], state='readonly')
        yscale_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(controls, text="Time Span:").pack(side=tk.LEFT, padx=5)
        self.timespan_var = tk.StringVar(value="50ms")
        timespan_combo = ttk.Combobox(controls, textvariable=self.timespan_var, width=10,
                                      values=["100µs", "200µs", "500µs", "1ms", "2ms", "5ms", "10ms", "25ms", "50ms", "100ms"], state='readonly')
        timespan_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(controls, text="Freeze", command=self.toggle_freeze).pack(side=tk.LEFT, padx=5)
        self.frozen = False
        
        # Start update loop
        self.update_plot()
    
    def toggle_freeze(self):
        """Toggle freeze/run mode."""
        self.frozen = not self.frozen
    
    def on_close(self):
        """Handle window close."""
        self.is_running = False
        self.window.destroy()
    
    def update_plot(self):
        """Update the oscilloscope display."""
        if not self.is_running:
            return
        
        try:
            if not self.frozen:
                # Get waveform data (non-blocking)
                data = self.generator.get_scope_data(self.card_name, self.channel_number)
                
                if len(data) > 10:  # Ensure we have enough data
                    # Parse time span (handle µs, ms)
                    timespan_str = self.timespan_var.get()
                    if 'µs' in timespan_str:
                        # Microseconds to milliseconds
                        timespan_ms = float(timespan_str.replace('µs', '')) / 1000.0
                    else:
                        # Milliseconds
                        timespan_ms = float(timespan_str.replace('ms', ''))
                    
                    # Calculate how many samples to show using AI sample rate (200kS/s)
                    samples_to_show = int((timespan_ms / 1000.0) * self.generator.ai_sample_rate)
                    samples_to_show = min(samples_to_show, len(data))
                    
                    if samples_to_show > 0:
                        # Get last N samples
                        display_data = data[-samples_to_show:]
                        
                        # Create time axis in milliseconds using AI sample rate
                        time_ms = np.arange(len(display_data)) / self.generator.ai_sample_rate * 1000
                        
                        # Update plot
                        self.line.set_data(time_ms, display_data)
                        self.ax.set_xlim(0, timespan_ms)
                        
                        # Update Y scale
                        yscale = self.yscale_var.get()
                        if yscale == "Auto":
                            margin = max(np.max(np.abs(display_data)) * 0.1, 0.0001)
                            self.ax.set_ylim(np.min(display_data) - margin, np.max(display_data) + margin)
                        else:
                            # Parse scale value (handle µV, mV, V)
                            yscale_str = yscale.replace('±', '')
                            if 'µV' in yscale_str:
                                limit = float(yscale_str.replace('µV', '')) / 1e6
                            elif 'mV' in yscale_str:
                                limit = float(yscale_str.replace('mV', '')) / 1e3
                            else:
                                limit = float(yscale_str.replace('V', ''))
                            self.ax.set_ylim(-limit, limit)
                        
                        # Check for clipping (near ±10V)
                        max_val = np.max(np.abs(display_data))
                        if max_val > 9.5:
                            self.clip_text.set_text('⚠ CLIPPING DETECTED!')
                        elif max_val > 9.0:
                            self.clip_text.set_text('⚠ Near Clipping')
                        else:
                            self.clip_text.set_text('')
                        
                        # Update stats with samples per cycle info
                        rms = np.sqrt(np.mean(display_data**2))
                        peak = np.max(np.abs(display_data))
                        freq_est = self.generator.frequency
                        samples_per_cycle = self.generator.ai_sample_rate / freq_est
                        # Display in µV for better readability with high-gain amplifiers
                        rms_uv = rms * 1e6
                        peak_uv = peak * 1e6
                        stats = f'RMS: {rms_uv:.1f} µV\nPeak: {peak_uv:.1f} µV\nFreq: {freq_est:.1f} Hz\nSamples/Cycle: {samples_per_cycle:.1f}'
                        self.stats_text.set_text(stats)
                        
                        # Use draw_idle() instead of draw() - non-blocking
                        self.canvas.draw_idle()
        except Exception as e:
            # Don't let plotting errors stop the oscilloscope
            print(f"Oscilloscope update error: {e}")
        
        # Schedule next update
        if self.is_running:
            self.window.after(100, self.update_plot)  # Update at 10 Hz (less aggressive)


class PXIeControlGUI:
    """Professional GUI for controlling multiple PXIe-4468 cards."""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PXIe-4468 Multi-Card Sine Generator")
        self.root.geometry("1000x800")
        
        # Initialize managers
        self.freq_manager = FrequencyManager()
        self.generator = MultiCardGenerator()
        
        # Current state
        self.current_frequency = 1000.0
        self.current_sample_rate = 100000
        self.is_generating = False
        
        # Build UI
        self.setup_ui()
        
        # Load initial frequency
        self.update_frequency_selection()
        
        # Start periodic update of input measurements
        self.update_input_displays()
    
    def setup_ui(self):
        """Create the user interface."""
        # Top control panel
        control_frame = ttk.LabelFrame(self.root, text="Generation Control", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Frequency selection
        ttk.Label(control_frame, text="Frequency:").grid(row=0, column=0, sticky=tk.W, padx=5)
        
        self.freq_var = tk.StringVar()
        self.freq_combo = ttk.Combobox(control_frame, textvariable=self.freq_var, 
                                       width=20, state='readonly')
        
        available_freqs = self.freq_manager.get_available_frequencies()
        freq_options = [f"{f.frequency} Hz - {f.name}" for f in available_freqs]
        self.freq_combo['values'] = freq_options
        if freq_options:
            self.freq_combo.current(0)
        self.freq_combo.grid(row=0, column=1, padx=5)
        self.freq_combo.bind('<<ComboboxSelected>>', self.on_frequency_changed)
        
        # Sample rate display
        ttk.Label(control_frame, text="Sample Rate:").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.srate_label = ttk.Label(control_frame, text="100000 Hz", font=('Arial', 10, 'bold'))
        self.srate_label.grid(row=0, column=3, sticky=tk.W, padx=5)
        
        # Quality indicator
        ttk.Label(control_frame, text="Quality:").grid(row=0, column=4, sticky=tk.W, padx=5)
        self.quality_label = ttk.Label(control_frame, text="Good", 
                                       font=('Arial', 10, 'bold'), foreground='green')
        self.quality_label.grid(row=0, column=5, sticky=tk.W, padx=5)
        
        # Start/Stop buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.grid(row=1, column=0, columnspan=6, pady=10)
        
        self.start_btn = ttk.Button(button_frame, text="▶ Start Generation", 
                                    command=self.start_generation, width=20)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(button_frame, text="⏹ Stop Generation", 
                                   command=self.stop_generation, state=tk.DISABLED, width=20)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Create notebook for cards
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create tab for each card
        self.card_frames = {}
        self.channel_widgets = {}  # Store widgets for each channel
        
        for card_name in MultiCardGenerator.CARD_NAMES:
            tab = ttk.Frame(notebook)
            notebook.add(tab, text=f"Card {card_name}")
            
            self.card_frames[card_name] = tab
            self.create_card_panel(tab, card_name)
    
    def create_card_panel(self, parent: ttk.Frame, card_name: str):
        """Create control panel for one card."""
        # Header with card controls
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(header, text=f"Card: {card_name}", 
                 font=('Arial', 12, 'bold')).pack(side=tk.LEFT, padx=5)
        
        # Enable all / Disable all buttons
        ttk.Button(header, text="Enable All", 
                  command=lambda: self.set_all_channels(card_name, True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(header, text="Disable All", 
                  command=lambda: self.set_all_channels(card_name, False)).pack(side=tk.LEFT, padx=5)
        
        # Set all amplitudes
        ttk.Label(header, text="Set All Amplitudes:").pack(side=tk.LEFT, padx=5)
        amp_entry = ttk.Entry(header, width=10)
        amp_entry.pack(side=tk.LEFT, padx=2)
        ttk.Label(header, text="µV").pack(side=tk.LEFT)
        ttk.Button(header, text="Apply", 
                  command=lambda: self.set_all_amplitudes(card_name, amp_entry)).pack(side=tk.LEFT, padx=5)
        
        # Scrollable channel list
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Channel headers
        headers = ttk.Frame(scrollable_frame)
        headers.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(headers, text="Ch", width=6).pack(side=tk.LEFT, padx=5)
        ttk.Label(headers, text="En", width=4).pack(side=tk.LEFT, padx=5)
        ttk.Label(headers, text="Output (µV)", width=12).pack(side=tk.LEFT, padx=5)
        ttk.Label(headers, text="RMS (V)", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(headers, text="Peak (V)", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(headers, text="Status", width=12).pack(side=tk.LEFT, padx=5)
        ttk.Label(headers, text="Scope", width=8).pack(side=tk.LEFT, padx=5)
        
        # Create widgets for each channel
        for ch_num in range(MultiCardGenerator.CHANNELS_PER_CARD):
            channel = self.generator.get_channel(card_name, ch_num)
            if channel:
                self.create_channel_row(scrollable_frame, channel)
        
        canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")
    
    def create_channel_row(self, parent: ttk.Frame, channel: ChannelConfig):
        """Create control row for a single channel."""
        frame = ttk.Frame(parent, relief=tk.RIDGE, borderwidth=1)
        frame.pack(fill=tk.X, padx=5, pady=2)
        
        key = f"{channel.card_name}_ch{channel.channel_number}"
        
        # Channel label
        ttk.Label(frame, text=f"AO{channel.channel_number}", 
                 width=6, font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=5)
        
        # Enable checkbox
        enabled_var = tk.BooleanVar(value=channel.enabled)
        enabled_check = ttk.Checkbutton(frame, variable=enabled_var,
                                       command=lambda: self.on_channel_enabled_changed(channel, enabled_var))
        enabled_check.pack(side=tk.LEFT, padx=5)
        
        # Amplitude entry
        amp_var = tk.StringVar(value=str(channel.amplitude_uv))
        amp_entry = ttk.Entry(frame, textvariable=amp_var, width=12)
        amp_entry.pack(side=tk.LEFT, padx=5)
        amp_entry.bind('<Return>', lambda e: self.on_amplitude_changed(channel, amp_var))
        amp_entry.bind('<FocusOut>', lambda e: self.on_amplitude_changed(channel, amp_var))
        
        # Input RMS display
        rms_label = ttk.Label(frame, text="0.000 V", width=10, anchor=tk.E, 
                             font=('Courier', 9), foreground='blue')
        rms_label.pack(side=tk.LEFT, padx=5)
        
        # Input peak display
        peak_label = ttk.Label(frame, text="0.000 V", width=10, anchor=tk.E,
                              font=('Courier', 9), foreground='darkgreen')
        peak_label.pack(side=tk.LEFT, padx=5)
        
        # Status label
        status_label = ttk.Label(frame, text="Idle", width=12, foreground='gray')
        status_label.pack(side=tk.LEFT, padx=5)
        
        # Oscilloscope button
        scope_btn = ttk.Button(frame, text="📊 Scope", width=8,
                              command=lambda: self.open_oscilloscope(channel))
        scope_btn.pack(side=tk.LEFT, padx=5)
        
        # Store widgets for later access
        self.channel_widgets[key] = {
            'enabled_var': enabled_var,
            'amp_var': amp_var,
            'rms_label': rms_label,
            'peak_label': peak_label,
            'status_label': status_label
        }
    
    def open_oscilloscope(self, channel: ChannelConfig):
        """Open oscilloscope window for a specific channel."""
        if not self.is_generating:
            messagebox.showinfo("Oscilloscope", 
                              "Please start generation first to view waveforms.")
            return
        
        try:
            # Create oscilloscope window (non-blocking)
            print(f"Opening oscilloscope for {channel.card_name}/AI{channel.channel_number}...")
            OscilloscopeWindow(self.root, self.generator, 
                              channel.card_name, channel.channel_number)
            print("Oscilloscope window opened successfully")
        except Exception as e:
            print(f"Error opening oscilloscope: {e}")
            messagebox.showerror("Oscilloscope Error", 
                               f"Failed to open oscilloscope:\n{e}")
    
    def on_frequency_changed(self, event=None):
        """Handle frequency selection change."""
        self.update_frequency_selection()
    
    def update_frequency_selection(self):
        """Update frequency and sample rate based on selection."""
        try:
            selected = self.freq_var.get()
            if not selected:
                return
            
            # Parse frequency from selection
            freq_str = selected.split(' ')[0]
            frequency = float(freq_str)
            
            # Calculate optimal sample rate
            sample_rate = self.freq_manager.calculate_sample_rate(frequency)
            
            self.current_frequency = frequency
            self.current_sample_rate = sample_rate
            
            # Update display
            self.srate_label.config(text=f"{sample_rate:,} Hz")
            
            # Update quality indicator
            samples_per_cycle = sample_rate / frequency
            if samples_per_cycle >= 100:
                self.quality_label.config(text="Excellent", foreground='darkgreen')
            elif samples_per_cycle >= 50:
                self.quality_label.config(text="Good", foreground='green')
            elif samples_per_cycle >= 20:
                self.quality_label.config(text="Fair", foreground='orange')
            else:
                self.quality_label.config(text="Poor", foreground='red')
            
            # Update generator if running
            if self.is_generating:
                self.generator.set_frequency(frequency, sample_rate)
            
            self.status_var.set(f"Frequency: {frequency} Hz, Sample Rate: {sample_rate:,} Hz, "
                              f"Samples/Cycle: {samples_per_cycle:.1f}")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update frequency: {e}")
    
    def on_channel_enabled_changed(self, channel: ChannelConfig, enabled_var: tk.BooleanVar):
        """Handle channel enable/disable."""
        enabled = enabled_var.get()
        self.generator.set_channel_enabled(channel.card_name, channel.channel_number, enabled)
        
        # Update status
        key = f"{channel.card_name}_ch{channel.channel_number}"
        if key in self.channel_widgets:
            status_label = self.channel_widgets[key]['status_label']
            if enabled:
                status_label.config(text="Enabled" if self.is_generating else "Ready", 
                                  foreground='green')
            else:
                status_label.config(text="Disabled", foreground='gray')
    
    def on_amplitude_changed(self, channel: ChannelConfig, amp_var: tk.StringVar):
        """Handle amplitude change."""
        try:
            amplitude_uv = float(amp_var.get())
            if amplitude_uv < 0:
                raise ValueError("Amplitude must be positive")
            
            self.generator.set_channel_amplitude(channel.card_name, 
                                                channel.channel_number, 
                                                amplitude_uv)
            
            # Update status
            key = f"{channel.card_name}_ch{channel.channel_number}"
            if key in self.channel_widgets:
                status_label = self.channel_widgets[key]['status_label']
                amp_mv = amplitude_uv / 1000
                if amp_mv >= 1:
                    status_label.config(text=f"{amp_mv:.2f} mV")
                else:
                    status_label.config(text=f"{amplitude_uv:.0f} µV")
        
        except ValueError as e:
            messagebox.showerror("Invalid Amplitude", 
                               f"Please enter a valid positive number.\n{e}")
            amp_var.set(str(channel.amplitude_uv))
    
    def set_all_channels(self, card_name: str, enabled: bool):
        """Enable or disable all channels on a card."""
        for ch_num in range(MultiCardGenerator.CHANNELS_PER_CARD):
            channel = self.generator.get_channel(card_name, ch_num)
            if channel:
                self.generator.set_channel_enabled(card_name, ch_num, enabled)
                
                # Update UI
                key = f"{card_name}_ch{ch_num}"
                if key in self.channel_widgets:
                    self.channel_widgets[key]['enabled_var'].set(enabled)
                    status_label = self.channel_widgets[key]['status_label']
                    if enabled:
                        status_label.config(text="Enabled" if self.is_generating else "Ready", 
                                          foreground='green')
                    else:
                        status_label.config(text="Disabled", foreground='gray')
    
    def set_all_amplitudes(self, card_name: str, amp_entry: ttk.Entry):
        """Set amplitude for all channels on a card."""
        try:
            amplitude_uv = float(amp_entry.get())
            if amplitude_uv < 0:
                raise ValueError("Amplitude must be positive")
            
            for ch_num in range(MultiCardGenerator.CHANNELS_PER_CARD):
                channel = self.generator.get_channel(card_name, ch_num)
                if channel:
                    self.generator.set_channel_amplitude(card_name, ch_num, amplitude_uv)
                    
                    # Update UI
                    key = f"{card_name}_ch{ch_num}"
                    if key in self.channel_widgets:
                        self.channel_widgets[key]['amp_var'].set(str(amplitude_uv))
            
            self.status_var.set(f"Set all channels on {card_name} to {amplitude_uv} µV")
        
        except ValueError as e:
            messagebox.showerror("Invalid Amplitude", 
                               f"Please enter a valid positive number.\n{e}")
    
    def start_generation(self):
        """Start sine wave generation."""
        try:
            # Update generator with current frequency and sample rate
            self.generator.set_frequency(self.current_frequency, self.current_sample_rate)
            
            # Start generation
            result = self.generator.start_generation()
            
            if "No channels enabled" in result:
                messagebox.showwarning("No Channels", result)
                return
            
            self.is_generating = True
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_var.set(f"Generating: {self.current_frequency} Hz at "
                              f"{self.current_sample_rate:,} Hz - {result}")
            
            # Update all enabled channel statuses
            for key, widgets in self.channel_widgets.items():
                if widgets['enabled_var'].get():
                    widgets['status_label'].config(text="Active", foreground='darkgreen')
        
        except Exception as e:
            messagebox.showerror("Generation Error", f"Failed to start generation:\n{e}")
    
    def stop_generation(self):
        """Stop sine wave generation."""
        try:
            self.generator.stop_generation()
            self.is_generating = False
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.status_var.set("Stopped")
            
            # Update all channel statuses
            for key, widgets in self.channel_widgets.items():
                if widgets['enabled_var'].get():
                    widgets['status_label'].config(text="Ready", foreground='green')
                else:
                    widgets['status_label'].config(text="Disabled", foreground='gray')
                # Clear input displays
                widgets['rms_label'].config(text="0.000 V")
                widgets['peak_label'].config(text="0.000 V")
        
        except Exception as e:
            messagebox.showerror("Stop Error", f"Failed to stop generation:\n{e}")
    
    def update_input_displays(self):
        """Periodically update input measurement displays."""
        if self.is_generating:
            # Update each enabled channel's input measurements
            for key, widgets in self.channel_widgets.items():
                if widgets['enabled_var'].get():
                    # Parse card name and channel from key (e.g., "SV1_ch0")
                    parts = key.split('_ch')
                    if len(parts) == 2:
                        card_name = parts[0]
                        ch_num = int(parts[1])
                        
                        # Get measurements from generator
                        measurements = self.generator.get_input_measurements(card_name, ch_num)
                        rms = measurements.get('rms', 0.0)
                        peak = measurements.get('peak', 0.0)
                        
                        # Update display labels
                        widgets['rms_label'].config(text=f"{rms:.6f} V")
                        widgets['peak_label'].config(text=f"{peak:.6f} V")
        
        # Schedule next update (100ms)
        self.root.after(100, self.update_input_displays)


def connect_to_chassis():
    """Connect to the PXIe chassis and list available devices."""
    try:
        system = nidaqmx.system.System.local()
        
        print("Connecting to PXIe chassis...")
        print(f"NI-DAQmx Driver Version: {system.driver_version}")
        
        devices = system.devices
        
        if not devices:
            print("No devices found. Make sure the PXIe chassis is connected via Thunderbolt.")
            return None
        
        print(f"\nFound {len(devices)} device(s):")
        for device in devices:
            print(f"  - Device Name: {device.name}")
            print(f"    Product Type: {device.product_type}")
            print(f"    Serial Number: {device.serial_num}")
            print(f"    AI Channels: {len(device.ai_physical_chans)}")
            print(f"    AO Channels: {len(device.ao_physical_chans)}")
            print()
        
        return True
            
    except Exception as e:
        print(f"Error connecting to chassis: {e}")
        return None


def main():
    """Main function to run the application."""
    print("=" * 60)
    print("PXIe-4468 Multi-Card Sine Wave Generator")
    print("=" * 60)
    
    # Check connection to chassis
    if connect_to_chassis():
        print("\nLaunching GUI...")
        
        # Create and run GUI
        root = tk.Tk()
        app = PXIeControlGUI(root)
        root.mainloop()
    else:
        print("\nFailed to connect to PXIe chassis.")
        print("Please ensure:")
        print("  1. The PXIe chassis is powered on")
        print("  2. Thunderbolt connection is active")
        print("  3. NI-DAQmx drivers are installed")
        print("  4. Device names are configured as SV1, SV2, SV3, SV4 in NI MAX")


if __name__ == "__main__":
    main()
