"""
Simple test script to verify PXIe-4468 setup and connectivity.
Run this before using the main application.
"""

import sys

def test_imports():
    """Test if all required packages are installed."""
    print("=" * 60)
    print("Testing Python Package Imports")
    print("=" * 60)
    
    packages = {
        'nidaqmx': 'NI-DAQmx Python API',
        'numpy': 'NumPy',
        'tkinter': 'Tkinter GUI'
    }
    
    all_ok = True
    for package, name in packages.items():
        try:
            __import__(package)
            print(f"✓ {name:30} - OK")
        except ImportError as e:
            print(f"✗ {name:30} - FAILED: {e}")
            all_ok = False
    
    return all_ok


def test_nidaqmx():
    """Test NI-DAQmx connection and list devices."""
    print("\n" + "=" * 60)
    print("Testing NI-DAQmx Connection")
    print("=" * 60)
    
    try:
        import nidaqmx.system
        system = nidaqmx.system.System.local()
        
        print(f"✓ NI-DAQmx Driver Version: {system.driver_version}")
        
        devices = system.devices
        
        if not devices:
            print("\n⚠ WARNING: No devices found!")
            print("  - Check PXIe chassis power")
            print("  - Verify Thunderbolt connection")
            print("  - Open NI MAX to verify device detection")
            return False
        
        print(f"\n✓ Found {len(devices)} device(s):\n")
        
        target_cards = ['SV1', 'SV2', 'SV3', 'SV4']
        found_cards = []
        
        for device in devices:
            is_target = device.name in target_cards
            marker = "✓" if is_target else " "
            
            print(f"{marker} Device: {device.name}")
            print(f"  Product: {device.product_type}")
            print(f"  Serial: {device.serial_num}")
            print(f"  AO Channels: {len(device.ao_physical_chans)}")
            
            if "4468" in device.product_type:
                print(f"  → PXIe-4468 detected!")
            
            if is_target:
                found_cards.append(device.name)
            
            print()
        
        # Check for target cards
        missing_cards = set(target_cards) - set(found_cards)
        
        if missing_cards:
            print("\n⚠ CONFIGURATION WARNING:")
            print(f"  Expected cards not found: {', '.join(missing_cards)}")
            print("\n  To fix:")
            print("  1. Open NI Measurement & Automation Explorer (NI MAX)")
            print("  2. Find your PXIe-4468 devices")
            print("  3. Rename them to: SV1, SV2, SV3, SV4")
            print("  4. Rerun this test")
        else:
            print("✓ All target cards found (SV1, SV2, SV3, SV4)")
        
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        print("\nPossible causes:")
        print("  - NI-DAQmx drivers not installed")
        print("  - PXIe chassis not connected")
        print("  - Thunderbolt connection issue")
        return False


def test_frequencies_csv():
    """Test if frequencies.CSV exists and is readable."""
    print("\n" + "=" * 60)
    print("Testing Frequencies CSV File")
    print("=" * 60)
    
    import os
    import csv
    
    csv_path = "frequencies.CSV"
    
    if not os.path.exists(csv_path):
        print(f"✗ File not found: {csv_path}")
        return False
    
    print(f"✓ File exists: {csv_path}")
    
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            frequencies = []
            
            for row in reader:
                try:
                    freq = float(row['Frequency'])
                    name = row.get('Name', f"{freq} Hz")
                    available = row.get('Available', '').strip().upper() == 'X'
                    enabled = row.get('Enabled', '').strip().upper() == 'X'
                    
                    if available or enabled:
                        frequencies.append((freq, name))
                except (ValueError, KeyError):
                    continue
        
        print(f"✓ Loaded {len(frequencies)} available frequencies")
        
        if frequencies:
            print("\nFirst 10 frequencies:")
            for freq, name in frequencies[:10]:
                print(f"  - {freq:8.0f} Hz : {name}")
            
            if len(frequencies) > 10:
                print(f"  ... and {len(frequencies) - 10} more")
        
        return True
        
    except Exception as e:
        print(f"✗ Error reading file: {e}")
        return False


def main():
    """Run all tests."""
    print("\nPXIe-4468 Setup Verification")
    print("Testing system configuration...\n")
    
    results = []
    
    # Test imports
    results.append(("Package Imports", test_imports()))
    
    # Test NI-DAQmx
    results.append(("NI-DAQmx Connection", test_nidaqmx()))
    
    # Test CSV
    results.append(("Frequencies CSV", test_frequencies_csv()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "PASS" if passed else "FAIL"
        symbol = "✓" if passed else "✗"
        print(f"{symbol} {test_name:25} - {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    
    if all_passed:
        print("✓ ALL TESTS PASSED")
        print("\nYou can now run: python main.py")
    else:
        print("✗ SOME TESTS FAILED")
        print("\nPlease fix the issues above before running the main application.")
    
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
