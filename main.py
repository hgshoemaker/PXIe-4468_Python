"""
Main Python application entry point for PXIe-4468 data acquisition.
"""

import nidaqmx
import nidaqmx.system
import numpy as np
import time
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Slider, Button
from threading import Thread, Event, Lock


def connect_to_chassis():
    """Connect to the PXIe chassis over Thunderbolt and list available devices."""
    try:
        # Create a system object to interact with NI-DAQmx
        system = nidaqmx.system.System.local()
        
        print("Connecting to PXIe chassis...")
        print(f"NI-DAQmx Driver Version: {system.driver_version}")
        
        # List all devices in the system
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
        
        # Return the first PXIe-4468 device found
        for device in devices:
            if "4468" in device.product_type:
                print(f"PXIe-4468 device found: {device.name}")
                return device.name
        
        # If no 4468 found, return the first device
        if devices:
            print(f"Using device: {devices[0].name}")
            return devices[0].name
            
    except Exception as e:
        print(f"Error connecting to chassis: {e}")
        return None


def generate_sinewave(frequency, amplitude, sample_rate, duration, offset=0.0):
    """
    Generate a sine wave signal with optional DC offset.
    
    Args:
        frequency: Frequency in Hz
        amplitude: Peak amplitude in volts
        sample_rate: Samples per second
        duration: Duration in seconds
        offset: DC offset in volts (default: 0.0)
    
    Returns:
        numpy array of sine wave samples
    """
    num_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, num_samples, endpoint=False)
    sine_wave = offset + amplitude * np.sin(2 * np.pi * frequency * t)
    return sine_wave


def output_continuous_sinewave(device_name="Dev1", channel="ao1", 
                               frequency=50000.0, amplitude=0.1, 
                               sample_rate=1000000):
    """
    Output a continuous sine wave on the specified analog output channel.
    
    Args:
        device_name: Name of the DAQ device (default: "Dev1")
        channel: Analog output channel (default: "ao1")
        frequency: Sine wave frequency in Hz (default: 1000 Hz)
        amplitude: Peak amplitude in volts (default: 1.0 V)
        sample_rate: Sample rate in Hz (default: 50000 Hz)
    """
    try:
        # Generate one period of the sine wave
        period = 1.0 / frequency
        samples = generate_sinewave(frequency, amplitude, sample_rate, period)
        
        print(f"Configuring {device_name}/{channel}:")
        print(f"  Frequency: {frequency} Hz")
        print(f"  Amplitude: {amplitude} V")
        print(f"  Sample Rate: {sample_rate} Hz")
        print(f"  Samples per period: {len(samples)}")
        
        # Create analog output task
        with nidaqmx.Task() as task:
            # Add analog output channel
            task.ao_channels.add_ao_voltage_chan(f"{device_name}/{channel}")
            
            # Configure timing for continuous output
            task.timing.cfg_samp_clk_timing(
                rate=sample_rate,
                sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS,
                samps_per_chan=len(samples)
            )
            
            # Enable regeneration so the waveform repeats
            task.out_stream.regen_mode = nidaqmx.constants.RegenerationMode.ALLOW_REGENERATION
            
            # Write the waveform to the buffer
            task.write(samples, auto_start=False)
            
            # Start the task
            task.start()
            
            print("\nSine wave output started. Press Ctrl+C to stop...")
            
            # Keep the task running until interrupted
            try:
                while True:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("\nStopping output...")
                task.stop()
                print("Output stopped.")
                
    except nidaqmx.DaqError as e:
        print(f"\nDAQmx Error: {e}")
    except Exception as e:
        print(f"\nError: {e}")


class InteractiveOscilloscope:
    """Interactive oscilloscope with real-time controls."""
    
    def __init__(self, device_name="Dev1", ao_channel="ao1", ai_channel="ai1",
                 initial_frequency=1000.0, initial_amplitude=1.0, sample_rate=50000):
        """
        Initialize the interactive oscilloscope.
        
        Args:
            device_name: Name of the DAQ device
            ao_channel: Analog output channel
            ai_channel: Analog input channel to monitor
            initial_frequency: Initial frequency in Hz
            initial_amplitude: Initial amplitude in volts
            sample_rate: Sample rate in Hz
        """
        self.device_name = device_name
        self.ao_channel = ao_channel
        self.ai_channel = ai_channel
        self.sample_rate = sample_rate
        self.display_samples = 5000
        
        # Signal parameters (thread-safe)
        self.lock = Lock()
        self.frequency = initial_frequency
        self.amplitude = initial_amplitude
        self.offset = 0.0
        self.sample_rate_value = sample_rate
        self.sample_rate_changed = False
        self.y_min = -5.0
        self.y_max = 5.0
        self.auto_scale = True
        
        # Data buffers
        self.input_data = np.zeros(self.display_samples)
        self.stop_event = Event()
        self.ao_task = None
        self.ai_task = None
        
        # Set up the plot with controls
        self.fig = plt.figure(figsize=(15, 9))
        
        # Main plot area - adjusted to make room for more controls
        self.ax = plt.axes([0.1, 0.35, 0.85, 0.55])
        self.line, = self.ax.plot(self.input_data, 'b-', linewidth=1)
        self.ax.set_ylim(self.y_min, self.y_max)
        self.ax.set_xlim(0, self.display_samples)
        self.ax.set_ylabel('Voltage (V)', fontsize=11)
        self.ax.set_title(f'Interactive Oscilloscope - Output: {ao_channel} | Input: {ai_channel}', 
                         fontsize=12, fontweight='bold')
        self.ax.grid(True, alpha=0.3)
        
        time_span = self.display_samples / sample_rate
        self.ax.set_xlabel(f'Samples (Time span: {time_span*1000:.1f} ms)', fontsize=11)
        
        # Output Generator Controls Section
        gen_label_y = 0.29
        self.fig.text(0.05, gen_label_y, 'Generator Output:', fontsize=11, fontweight='bold')
        
        ax_freq = plt.axes([0.15, 0.25, 0.7, 0.02])
        ax_amp = plt.axes([0.15, 0.22, 0.7, 0.02])
        ax_offset = plt.axes([0.15, 0.19, 0.7, 0.02])
        
        self.slider_freq = Slider(ax_freq, 'Frequency (Hz)', 10, 50000, 
                                   valinit=initial_frequency, valstep=10)
        self.slider_amp = Slider(ax_amp, 'Amplitude (V)', 0.0, 10.0, 
                                  valinit=initial_amplitude, valstep=0.1)
        self.slider_offset = Slider(ax_offset, 'DC Offset (V)', -10.0, 10.0,
                                     valinit=0.0, valstep=0.1)
        
        # Oscilloscope Controls Section
        scope_label_y = 0.16
        self.fig.text(0.05, scope_label_y, 'Oscilloscope:', fontsize=11, fontweight='bold')
        
        ax_srate = plt.axes([0.15, 0.12, 0.7, 0.02])
        ax_ymin = plt.axes([0.15, 0.08, 0.7, 0.02])
        ax_ymax = plt.axes([0.15, 0.04, 0.7, 0.02])
        
        self.slider_srate = Slider(ax_srate, 'Sample Rate (Hz)', 1000, 200000,
                                    valinit=sample_rate, valstep=1000)
        self.slider_ymin = Slider(ax_ymin, 'Y Min (V)', -20, 0, 
                                   valinit=self.y_min, valstep=0.5)
        self.slider_ymax = Slider(ax_ymax, 'Y Max (V)', 0, 20, 
                                   valinit=self.y_max, valstep=0.5)
        
        # Auto-scale button
        ax_auto = plt.axes([0.88, 0.08, 0.1, 0.04])
        self.btn_auto = Button(ax_auto, 'Auto Scale')
        
        # Connect slider callbacks
        self.slider_freq.on_changed(self.update_frequency)
        self.slider_amp.on_changed(self.update_amplitude)
        self.slider_offset.on_changed(self.update_offset)
        self.slider_srate.on_changed(self.update_sample_rate)
        self.slider_ymin.on_changed(self.update_ymin)
        self.slider_ymax.on_changed(self.update_ymax)
        self.btn_auto.on_clicked(self.toggle_auto_scale)
        
        # Add info text
        self.info_text = self.ax.text(0.02, 0.98, '', transform=self.ax.transAxes,
                                      verticalalignment='top', fontsize=9,
                                      bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        # Add warning text (initially hidden)
        self.warning_text = self.ax.text(0.98, 0.98, '', transform=self.ax.transAxes,
                                         verticalalignment='top', horizontalalignment='right',
                                         fontsize=9, color='red', fontweight='bold',
                                         bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.8))
        
    def update_frequency(self, val):
        """Callback for frequency slider."""
        with self.lock:
            self.frequency = val
    
    def update_amplitude(self, val):
        """Callback for amplitude slider."""
        with self.lock:
            self.amplitude = val
    
    def update_offset(self, val):
        """Callback for DC offset slider."""
        with self.lock:
            self.offset = val
    
    def update_sample_rate(self, val):
        """Callback for sample rate slider."""
        with self.lock:
            self.sample_rate_value = int(val)
            self.sample_rate_changed = True
        # Update time span label
        time_span = self.display_samples / self.sample_rate_value
        self.ax.set_xlabel(f'Samples (Time span: {time_span*1000:.1f} ms)', fontsize=11)
    
    def update_ymin(self, val):
        """Callback for Y-min slider."""
        self.y_min = val
        self.auto_scale = False
        self.ax.set_ylim(self.y_min, self.y_max)
    
    def update_ymax(self, val):
        """Callback for Y-max slider."""
        self.y_max = val
        self.auto_scale = False
        self.ax.set_ylim(self.y_min, self.y_max)
    
    def toggle_auto_scale(self, event):
        """Toggle auto-scaling."""
        self.auto_scale = not self.auto_scale
        status = "ON" if self.auto_scale else "OFF"
        print(f"Auto-scale: {status}")
    
    def output_thread(self):
        """Background thread for analog output."""
        current_task = None
        try:
            while not self.stop_event.is_set():
                # Get current parameters
                with self.lock:
                    freq = self.frequency
                    amp = self.amplitude
                    offset = self.offset
                    srate = self.sample_rate_value
                    rate_changed = self.sample_rate_changed
                    self.sample_rate_changed = False
                
                # Ensure minimum samples per cycle (at least 2, but prefer 10 minimum)
                samples_per_cycle = srate / freq
                if samples_per_cycle < 2:
                    print(f"WARNING: Frequency too high ({freq} Hz) for sample rate ({srate} Hz). Skipping update.")
                    time.sleep(0.1)
                    continue
                
                # Create new task if needed (initial or sample rate changed)
                if current_task is None or rate_changed:
                    if current_task is not None:
                        try:
                            current_task.stop()
                            current_task.close()
                        except:
                            pass
                    
                    current_task = nidaqmx.Task()
                    self.ao_task = current_task
                    current_task.ao_channels.add_ao_voltage_chan(f"{self.device_name}/{self.ao_channel}")
                    
                    period = 1.0 / freq
                    samples = generate_sinewave(freq, amp, srate, period, offset)
                    
                    # Ensure at least 2 samples
                    if len(samples) < 2:
                        print(f"ERROR: Not enough samples ({len(samples)}). Skipping.")
                        continue
                    
                    current_task.timing.cfg_samp_clk_timing(
                        rate=srate,
                        sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS,
                        samps_per_chan=len(samples)
                    )
                    current_task.out_stream.regen_mode = nidaqmx.constants.RegenerationMode.ALLOW_REGENERATION
                    current_task.write(samples, auto_start=False)
                    current_task.start()
                    
                    last_freq = freq
                    last_amp = amp
                    last_offset = offset
                    last_srate = srate
                    
                    if rate_changed:
                        print(f"Sample rate changed to {srate} Hz")
                else:
                    # Update waveform if frequency, amplitude, or offset changed
                    if freq != last_freq or amp != last_amp or offset != last_offset:
                        period = 1.0 / freq
                        samples = generate_sinewave(freq, amp, srate, period, offset)
                        
                        # Ensure at least 2 samples
                        if len(samples) < 2:
                            print(f"ERROR: Not enough samples ({len(samples)}). Skipping.")
                            time.sleep(0.1)
                            continue
                        
                        current_task.stop()
                        
                        # Reconfigure with new sample count if needed
                        current_task.timing.cfg_samp_clk_timing(
                            rate=srate,
                            sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS,
                            samps_per_chan=len(samples)
                        )
                        current_task.write(samples, auto_start=False)
                        current_task.start()
                        
                        last_freq = freq
                        last_amp = amp
                        last_offset = offset
                
                time.sleep(0.1)
            
            if current_task is not None:
                current_task.stop()
                current_task.close()
                
        except Exception as e:
            print(f"Output error: {e}")
            if current_task is not None:
                try:
                    current_task.close()
                except:
                    pass
    
    def acquisition_thread(self):
        """Background thread for continuous data acquisition."""
        current_task = None
        last_srate = None
        
        try:
            while not self.stop_event.is_set():
                # Check if sample rate changed
                with self.lock:
                    srate = self.sample_rate_value
                
                # Recreate task if sample rate changed
                if current_task is None or srate != last_srate:
                    if current_task is not None:
                        try:
                            current_task.stop()
                            current_task.close()
                        except:
                            pass
                    
                    current_task = nidaqmx.Task()
                    self.ai_task = current_task
                    current_task.ai_channels.add_ai_voltage_chan(f"{self.device_name}/{self.ai_channel}")
                    
                    current_task.timing.cfg_samp_clk_timing(
                        rate=srate,
                        sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS,
                        samps_per_chan=self.display_samples
                    )
                    
                    current_task.start()
                    last_srate = srate
                
                # Read data
                try:
                    samples = current_task.read(number_of_samples_per_channel=self.display_samples)
                    self.input_data = np.array(samples)
                except:
                    pass  # Handle buffer errors gracefully
                
                time.sleep(0.05)
            
            if current_task is not None:
                current_task.stop()
                current_task.close()
                
        except nidaqmx.DaqError as e:
            print(f"\nDAQmx Error in acquisition: {e}")
        except Exception as e:
            print(f"\nError in acquisition: {e}")
        finally:
            if current_task is not None:
                try:
                    current_task.close()
                except:
                    pass
    
    def animate(self, frame):
        """Animation function to update the plot."""
        self.line.set_ydata(self.input_data)
        
        # Auto-scale Y-axis based on data
        if self.auto_scale and len(self.input_data) > 0:
            data_min, data_max = np.min(self.input_data), np.max(self.input_data)
            margin = max((data_max - data_min) * 0.1, 0.5)
            self.y_min = data_min - margin
            self.y_max = data_max + margin
            self.ax.set_ylim(self.y_min, self.y_max)
            
            # Update sliders without triggering callbacks
            self.slider_ymin.eventson = False
            self.slider_ymax.eventson = False
            self.slider_ymin.set_val(self.y_min)
            self.slider_ymax.set_val(self.y_max)
            self.slider_ymin.eventson = True
            self.slider_ymax.eventson = True
        
        # Update info text
        with self.lock:
            freq = self.frequency
            amp = self.amplitude
            offset = self.offset
            srate = self.sample_rate_value
        
        # Calculate samples per cycle
        samples_per_cycle = srate / freq if freq > 0 else 0
        
        # Generate info text
        if len(self.input_data) > 0:
            rms = np.sqrt(np.mean(self.input_data**2))
            peak = np.max(np.abs(self.input_data))
            info = f'Output: {freq:.1f} Hz, {amp:.2f} V, Offset: {offset:.2f} V @ {srate/1000:.0f} kS/s\nSamples/Cycle: {samples_per_cycle:.1f} | Input RMS: {rms:.3f} V | Peak: {peak:.3f} V'
        else:
            info = f'Output: {freq:.1f} Hz, {amp:.2f} V, Offset: {offset:.2f} V\nSamples/Cycle: {samples_per_cycle:.1f}'
        
        self.info_text.set_text(info)
        
        # Update warning text based on samples per cycle
        if samples_per_cycle < 2:
            self.warning_text.set_text(f'⚠ ERROR\nInvalid!\n({samples_per_cycle:.1f} samples/cycle)\nMUST be ≥ 2\nReduce frequency!')
        elif samples_per_cycle < 10:
            self.warning_text.set_text(f'⚠ WARNING\nLow Quality\n({samples_per_cycle:.1f} samples/cycle)\nIncrease sample rate\nor decrease frequency')
        elif samples_per_cycle < 20:
            self.warning_text.set_text(f'⚠ CAUTION\nModerate Quality\n({samples_per_cycle:.1f} samples/cycle)')
        else:
            self.warning_text.set_text('')  # Clear warning
        
        return self.line, self.info_text, self.warning_text
    
    def start(self):
        """Start the interactive oscilloscope."""
        # Start output thread
        out_thread = Thread(target=self.output_thread, daemon=True)
        out_thread.start()
        
        # Start acquisition thread
        acq_thread = Thread(target=self.acquisition_thread, daemon=True)
        acq_thread.start()
        
        # Give threads time to start
        time.sleep(0.5)
        
        # Start animation
        ani = animation.FuncAnimation(
            self.fig, self.animate, interval=50, blit=True, cache_frame_data=False
        )
        
        plt.show()
        
        # Clean up when window is closed
        self.stop_event.set()
        time.sleep(0.2)
        if self.ao_task:
            try:
                self.ao_task.stop()
            except:
                pass
        if self.ai_task:
            try:
                self.ai_task.stop()
            except:
                pass


def run_interactive_oscilloscope(device_name="Dev1", ao_channel="ao1", ai_channel="ai1",
                                frequency=1000.0, amplitude=1.0, sample_rate=50000):
    """
    Run interactive oscilloscope with real-time controls.
    
    Args:
        device_name: Name of the DAQ device
        ao_channel: Analog output channel
        ai_channel: Analog input channel for monitoring
        frequency: Initial sine wave frequency in Hz
        amplitude: Initial peak amplitude in volts
        sample_rate: Sample rate in Hz
    """
    print(f"Starting interactive oscilloscope:")
    print(f"  Device: {device_name}")
    print(f"  Output: {ao_channel}")
    print(f"  Input: {ai_channel}")
    print(f"  Initial Frequency: {frequency} Hz")
    print(f"  Initial Amplitude: {amplitude} V")
    print(f"  Sample Rate: {sample_rate} Hz")
    print("\nUse the sliders to adjust parameters in real-time.")
    print("Close the plot window to stop.\n")
    
    # Create and start interactive oscilloscope
    scope = InteractiveOscilloscope(
        device_name=device_name,
        ao_channel=ao_channel,
        ai_channel=ai_channel,
        initial_frequency=frequency,
        initial_amplitude=amplitude,
        sample_rate=sample_rate
    )
    scope.start()


def main():
    """Main function to run the application."""
    device_name = connect_to_chassis()
    
    if device_name:
        print(f"\nSuccessfully connected to device: {device_name}")
        
        # Configuration parameters (easily adjustable)
        DEVICE = "Dev1"  # Change if your device has a different name
        AO_CHANNEL = "ao1"
        AI_CHANNEL = "ai1"
        FREQUENCY = 1000.0  # Hz - initial frequency
        AMPLITUDE = 1.0     # Volts - initial amplitude
        SAMPLE_RATE = 50000 # Hz - sample rate
        
        print(f"\nStarting interactive oscilloscope with controls...")
        run_interactive_oscilloscope(
            device_name=DEVICE,
            ao_channel=AO_CHANNEL,
            ai_channel=AI_CHANNEL,
            frequency=FREQUENCY,
            amplitude=AMPLITUDE,
            sample_rate=SAMPLE_RATE
        )
    else:
        print("\nFailed to connect to PXIe chassis.")


if __name__ == "__main__":
    main()
