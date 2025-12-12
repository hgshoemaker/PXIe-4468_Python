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
        """
        # Aim for at least 100 samples per cycle for good quality
        min_samples_per_cycle = 100
        base_rate = frequency * min_samples_per_cycle
        
        # Round to common sample rates
        common_rates = [1000, 2500, 5000, 10000, 25000, 50000, 100000, 
                       200000, 500000, 1000000, 2000000]
        
        for rate in common_rates:
            if rate >= base_rate:
                return rate
        
        # If frequency is very high, use maximum
        return 2000000  # 2 MS/s max for PXIe-4468


class MultiCardGenerator:
    """Manages sine wave generation across multiple PXIe-4468 cards."""
    
    CHANNELS_PER_CARD = 2  # PXIe-4468 has 2 analog outputs: ao0, ao1
    CARD_NAMES = ["SV1", "SV2", "SV3", "SV4"]
    
    def __init__(self):
        self.tasks: Dict[str, nidaqmx.Task] = {}
        self.lock = Lock()
        self.running = False
        self.stop_event = Event()
        
        # Current configuration
        self.frequency = 1000.0  # Hz
        self.sample_rate = 100000  # Hz
        self.channels: List[ChannelConfig] = []
        
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
        if self.running:
            return "Generator already running"
        
        # Check if any channels are enabled
        enabled_channels = [ch for ch in self.channels if ch.enabled]
        if not enabled_channels:
            return "No channels enabled. Please enable at least one channel."
        
        self.stop_event.clear()
        self.running = True
        self.output_thread = Thread(target=self._output_worker, daemon=True)
        self.output_thread.start()
        
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
        
        # Close all tasks
        for task_name, task in list(self.tasks.items()):
            try:
                task.stop()
                task.close()
            except:
                pass
        self.tasks.clear()
    
    def _output_worker(self):
        """Background thread that manages continuous output."""
        try:
            while not self.stop_event.is_set():
                with self.lock:
                    freq = self.frequency
                    srate = self.sample_rate
                    # Create copy of enabled channels
                    enabled_chs = [(ch.card_name, ch.channel_number, ch.amplitude_uv) 
                                  for ch in self.channels if ch.enabled]
                
                # Group channels by card
                cards = {}
                for card_name, ch_num, amp_uv in enabled_chs:
                    if card_name not in cards:
                        cards[card_name] = []
                    cards[card_name].append((ch_num, amp_uv))
                
                # Update tasks for each card
                for card_name, channel_list in cards.items():
                    task_name = card_name
                    
                    # Create task if it doesn't exist
                    if task_name not in self.tasks:
                        try:
                            task = nidaqmx.Task()
                            
                            # Add all channels for this card
                            for ch_num, _ in channel_list:
                                task.ao_channels.add_ao_voltage_chan(
                                    f"{card_name}/ao{ch_num}",
                                    min_val=-10.0,
                                    max_val=10.0
                                )
                            
                            # Configure timing
                            period = 1.0 / freq
                            samples = self.generate_sinewave(freq, 1.0, srate)  # 1V reference
                            
                            task.timing.cfg_samp_clk_timing(
                                rate=srate,
                                sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS,
                                samps_per_chan=len(samples)
                            )
                            task.out_stream.regen_mode = nidaqmx.constants.RegenerationMode.ALLOW_REGENERATION
                            
                            # Generate waveforms for each channel with individual amplitudes
                            waveforms = []
                            for ch_num, amp_uv in channel_list:
                                amp_v = amp_uv / 1e6  # Convert microvolts to volts
                                waveform = self.generate_sinewave(freq, amp_v, srate)
                                waveforms.append(waveform)
                            
                            # Write interleaved data
                            task.write(waveforms, auto_start=False)
                            task.start()
                            
                            self.tasks[task_name] = task
                            
                        except Exception as e:
                            print(f"Error creating task for {card_name}: {e}")
                            continue
                
                # Sleep for a bit before checking for updates
                time.sleep(0.1)
        
        except Exception as e:
            print(f"Output worker error: {e}")
        finally:
            # Clean up
            for task in list(self.tasks.values()):
                try:
                    task.stop()
                    task.close()
                except:
                    pass
            self.tasks.clear()


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
        ttk.Label(headers, text="Channel", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(headers, text="Enabled", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(headers, text="Amplitude (µV)", width=15).pack(side=tk.LEFT, padx=5)
        ttk.Label(headers, text="Status", width=20).pack(side=tk.LEFT, padx=5)
        
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
                 width=10).pack(side=tk.LEFT, padx=5)
        
        # Enable checkbox
        enabled_var = tk.BooleanVar(value=channel.enabled)
        enabled_check = ttk.Checkbutton(frame, variable=enabled_var,
                                       command=lambda: self.on_channel_enabled_changed(channel, enabled_var))
        enabled_check.pack(side=tk.LEFT, padx=5)
        
        # Amplitude entry
        amp_var = tk.StringVar(value=str(channel.amplitude_uv))
        amp_entry = ttk.Entry(frame, textvariable=amp_var, width=15)
        amp_entry.pack(side=tk.LEFT, padx=5)
        amp_entry.bind('<Return>', lambda e: self.on_amplitude_changed(channel, amp_var))
        amp_entry.bind('<FocusOut>', lambda e: self.on_amplitude_changed(channel, amp_var))
        
        # Status label
        status_label = ttk.Label(frame, text="Idle", width=20, foreground='gray')
        status_label.pack(side=tk.LEFT, padx=5)
        
        # Store widgets for later access
        self.channel_widgets[key] = {
            'enabled_var': enabled_var,
            'amp_var': amp_var,
            'status_label': status_label
        }
    
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
        
        except Exception as e:
            messagebox.showerror("Stop Error", f"Failed to stop generation:\n{e}")


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
