import psutil
import time
import os
import datetime
import math  # Added for math.isnan

# Attempt to import pythonnet and LibreHardwareMonitorLib
try:
    import clr

    # Ensure 'LibreHardwareMonitorLib.dll' is in the same directory as the script,
    # or in a directory listed in your system's PATH or Python's sys.path.
    clr.AddReference("LibreHardwareMonitorLib")
    from LibreHardwareMonitor import Hardware

    libre_hw_monitor_available = True
    libre_hw_monitor_error = None
except Exception as e:
    libre_hw_monitor_available = False
    libre_hw_monitor_error = str(e)  # Store the error message

# --- Configuration ---
UPDATE_INTERVAL = 2  # Seconds

# Auto-detect OS for default disk monitoring (can be overridden manually)
if os.name == 'nt':  # Windows
    DISKS_TO_MONITOR = ['C:\\']
    # Example for multiple disks on Windows: DISKS_TO_MONITOR = ['C:\\', 'D:\\']
else:  # Linux/macOS
    DISKS_TO_MONITOR = ['/']
    # Example for multiple disks on Linux/macOS: DISKS_TO_MONITOR = ['/', '/mnt/data']


# --- Helper Functions ---
def get_size_gb(bytes_val, suffix="B"):
    """
    Scale bytes to its proper format e.g:
    1253656 => '1.20MB'
    1253656678 => '1.17GB'
    """
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes_val < factor:
            return f"{bytes_val:.2f}{unit}{suffix}"
        bytes_val /= factor
    return f"{bytes_val:.2f}P{suffix}"


def clear_screen():
    """Clears the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


# Global variables for network speed calculation
last_net_io = psutil.net_io_counters()
last_time_net = time.time()


def get_network_speed():
    """Calculates network upload and download speed."""
    global last_net_io, last_time_net

    current_net_io = psutil.net_io_counters()
    current_time = time.time()

    elapsed_time = current_time - last_time_net
    if elapsed_time == 0:  # Avoid division by zero
        return 0.0, 0.0, current_net_io.bytes_sent, current_net_io.bytes_recv

    bytes_sent_diff = current_net_io.bytes_sent - last_net_io.bytes_sent
    bytes_recv_diff = current_net_io.bytes_recv - last_net_io.bytes_recv

    upload_speed = bytes_sent_diff / elapsed_time  # Bytes per second
    download_speed = bytes_recv_diff / elapsed_time  # Bytes per second

    last_net_io = current_net_io
    last_time_net = current_time

    return upload_speed, download_speed, current_net_io.bytes_sent, current_net_io.bytes_recv


def get_temperatures_lhm():
    """
    Retrieves temperatures using LibreHardwareMonitorLib.
    Returns a tuple: (temps_data, error_message_or_none)
    """
    temps_data = {}
    if not libre_hw_monitor_available:
        # This function shouldn't be called if not available, but as a safeguard:
        return temps_data, f"LibreHardwareMonitorLib not loaded. Stored error: {libre_hw_monitor_error}"

    try:
        computer = Hardware.Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuNvidiaEnabled = True  # For NVIDIA GPUs
        computer.IsGpuAmdEnabled = True  # For AMD GPUs
        # You can enable other hardware types if needed:
        # computer.IsMemoryEnabled = True
        # computer.IsMotherboardEnabled = True
        # computer.IsStorageEnabled = True
        computer.Open()

        for hardware_item in computer.Hardware:
            hardware_item.Update()  # Update sensors for this specific hardware item
            group_name = hardware_item.Name
            current_group_temps = []
            for sensor in hardware_item.Sensors:
                if sensor.SensorType == Hardware.SensorType.Temperature:
                    # Ensure sensor.Value is not None before trying to use it
                    temp_value = sensor.Value if sensor.Value is not None else float('nan')
                    current_group_temps.append({
                        "label": sensor.Name,
                        "current": temp_value
                    })
            if current_group_temps:  # Only add group if it has temperature sensors
                temps_data[group_name] = current_group_temps
        computer.Close()
        return temps_data, None
    except Exception as e:
        return {}, f"Error during LibreHardwareMonitor operation: {e}"


# --- Main Monitoring Function ---
def display_system_stats():
    """Gathers and displays system performance and temperature data."""
    print("System Performance & Temperature Monitor")
    print("----------------------------------------")
    print(f"Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Press Ctrl+C to exit.\n")

    # 1. CPU Usage
    print("--- CPU Usage ---")
    # Get per-core usage first. interval=None uses time since last call (or initial call in main)
    cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
    if cpu_per_core:  # Check if list is not empty
        cpu_overall = sum(cpu_per_core) / len(cpu_per_core)
        print(f"  Overall: {cpu_overall:.1f}% (avg of cores)")
    else:  # Fallback if percpu=True returns empty or fails, get a general reading
        cpu_overall = psutil.cpu_percent(interval=None)
        print(f"  Overall: {cpu_overall:.1f}%")

    for i, core_usage in enumerate(cpu_per_core):
        print(f"  Core {i + 1}:   {core_usage:.1f}%")
    print("")

    # 2. Memory Usage
    print("--- Memory Usage (RAM) ---")
    mem = psutil.virtual_memory()
    print(f"  Total:     {get_size_gb(mem.total)}")
    print(f"  Available: {get_size_gb(mem.available)}")
    print(f"  Used:      {get_size_gb(mem.used)} ({mem.percent:.1f}%)")
    print(f"  Free:      {get_size_gb(mem.free)}")
    swap = psutil.swap_memory()
    print(f"  Swap Total: {get_size_gb(swap.total)}")
    print(f"  Swap Used:  {get_size_gb(swap.used)} ({swap.percent:.1f}%)")
    print("")

    # 3. Disk Usage
    print("--- Disk Usage ---")
    for disk_path in DISKS_TO_MONITOR:
        try:
            disk = psutil.disk_usage(disk_path)
            print(f"  Disk ({disk_path}):")
            print(f"    Total:     {get_size_gb(disk.total)}")
            print(f"    Used:      {get_size_gb(disk.used)} ({disk.percent:.1f}%)")
            print(f"    Free:      {get_size_gb(disk.free)}")
        except FileNotFoundError:
            print(f"  Disk ({disk_path}): Not found or inaccessible.")
        except Exception as e:
            print(f"  Disk ({disk_path}): Error - {e}")
    print("")

    # 4. Network Activity
    print("--- Network Activity ---")
    upload_speed, download_speed, total_sent, total_recv = get_network_speed()
    print(f"  Total Sent:      {get_size_gb(total_sent)}")
    print(f"  Total Received:  {get_size_gb(total_recv)}")
    print(f"  Upload Speed:    {get_size_gb(upload_speed)}/s")
    print(f"  Download Speed:  {get_size_gb(download_speed)}/s")
    print("")

    # 5. System Temperatures / Heat
    print("--- System Temperatures ---")
    lhm_reported_temps = False
    if libre_hw_monitor_available:
        print("  Attempting to read temperatures using LibreHardwareMonitorLib...")
        lhm_temps, lhm_error_msg = get_temperatures_lhm()
        if lhm_error_msg:
            print(f"  LibreHardwareMonitor: Failed. Error: {lhm_error_msg}")
        elif not lhm_temps or not any(lhm_temps.values()):
            print("  LibreHardwareMonitor: No temperature sensors found or no data reported by sensors.")
        else:
            data_printed_for_lhm = False
            for group, entries in lhm_temps.items():
                if not entries: continue
                # Filter for entries that actually have a valid temperature reading
                valid_entries_in_group = [e for e in entries if
                                          isinstance(e['current'], float) and not math.isnan(e['current'])]
                if not valid_entries_in_group: continue

                print(f"  Sensor Group (LHM - {group}):")
                for entry in valid_entries_in_group:
                    print(f"    {entry['label']}: {entry['current']:.1f}°C")
                data_printed_for_lhm = True

            if data_printed_for_lhm:
                lhm_reported_temps = True
            else:
                print("  LibreHardwareMonitor: Sensors might be detected, but no valid temperature values available.")
    else:
        print(f"  LibreHardwareMonitorLib not found or failed to load. Error: {libre_hw_monitor_error}")
        print(
            "  (For temperature monitoring on Windows, download 'LibreHardwareMonitorLib.dll' and place it in the script's directory).")

    if not lhm_reported_temps:
        print("\n  Attempting fallback with psutil for temperatures...")
        try:
            psutil_temps_data = psutil.sensors_temperatures()
            if not psutil_temps_data:
                print("  psutil: Temperature sensors not found or not supported on this system.")
                if os.name != 'nt':  # Only show lm-sensors hint for non-Windows
                    print("  (On Linux, you might need 'lm-sensors' installed and configured.)")
            else:
                psutil_data_found = False
                for name, entries in psutil_temps_data.items():
                    if not entries: continue
                    print(f"  Sensor Group (psutil - {name}):")
                    for entry in entries:
                        label = f" ({entry.label})" if entry.label else ""
                        print(f"    {entry.current:.1f}°C{label}")
                        if entry.high:
                            print(f"      High: {entry.high:.1f}°C")
                        if entry.critical:
                            print(f"      Critical: {entry.critical:.1f}°C")
                        psutil_data_found = True
                if not psutil_data_found:
                    print(
                        "  psutil: No specific temperature data available from detected sensors (sensors might be present but not reporting values).")
        except AttributeError:
            print("  psutil: psutil.sensors_temperatures() not available on this platform/psutil version.")
        except Exception as e:
            print(f"  psutil: Could not retrieve temperatures: {e}")
            # print("  (You might need to run the script with administrator/root privileges for some sensors via psutil.)") # Already mentioned by LHM if it fails

    # Final check if any temperature was reported by any method
    # This check is implicitly handled by the flow above; if no temps, messages are already printed.
    print("")


if __name__ == "__main__":
    # Initial call to set baseline for CPU and network
    psutil.cpu_percent(interval=0.1)  # Establishes a baseline for subsequent non-blocking cpu_percent calls
    get_network_speed()  # Initial call for network
    time.sleep(0.1)  # Small delay

    try:
        while True:
            clear_screen()
            display_system_stats()
            print(f"\nUpdating in {UPDATE_INTERVAL} seconds...")
            time.sleep(UPDATE_INTERVAL)
    except KeyboardInterrupt:
        clear_screen()
        print("System monitor stopped by user.")
    except Exception as e:
        clear_screen()  # Clear screen before printing the final error
        print(f"An unexpected error occurred: {e}")
        if libre_hw_monitor_available is False and "LibreHardwareMonitorLib" in str(e):
            print("\nThis might be related to loading LibreHardwareMonitorLib.dll.")
            print("Ensure 'pythonnet' is installed (pip install pythonnet).")
            print("Ensure 'LibreHardwareMonitorLib.dll' is downloaded and placed in the same directory as this script.")
            print(f"Original import error: {libre_hw_monitor_error}")

