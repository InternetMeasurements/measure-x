# Script to periodically measure and log NTP time drift with a coordinator server
import subprocess
import time, csv
from datetime import datetime

COORDINATOR_IP = "192.168.1.123"  # IP address of the NTP coordinator
LOG_FILE = "ntp_drift_log.txt"     # Output log file
INTERVAL = 60 * 60  # Interval between measurements in seconds (1 hour)
time_counter = 8     # Number of measurements to perform

# Function to get the NTP offset and error by running ntpdate
def get_ntp_offset():
    try:
        result = subprocess.run(
            ["sudo", "ntpdate", COORDINATOR_IP],
            capture_output=True,
            text=True
        )
        output = result.stdout.split("\n")
        # Parse the output to extract offset and error
        for line in output:
            if COORDINATOR_IP in line:
                parts = line.split()
                offset = float(parts[3])  # Offset (ritardo)
                error = float(parts[5])   # Errore massimo stimato
                return offset, error
    except Exception as e:
        print(f"Errore nell'esecuzione di ntpdate: {e}")
        return None, None

# Function to log NTP drift measurements to a CSV file
def log_ntp_drift():
    with open(LOG_FILE, mode="w", newline="") as csv_file:
        fieldnames = ["Timestamp", "Offset (s)", "Max Error (s)"]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        try:
            for _ in range(time_counter):
                offset, error = get_ntp_offset()  # Get current offset and error
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Write the measurement to the CSV file
                writer.writerow({"Timestamp": timestamp, "Offset (s)": offset, "Max Error (s)": error})
                print(f"{timestamp}, Offset: {offset:.6f} s, Max error: {error:.6f} s")
                time.sleep(INTERVAL)  # Wait for the next measurement
        except KeyboardInterrupt:
            print("Measurement stopped from keyboard")
        finally:
            csv_file.close()

# Main entry point: start the logging process
if __name__ == "__main__":
    log_ntp_drift()