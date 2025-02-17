import subprocess
import time, csv
from datetime import datetime

COORDINATOR_IP = "192.168.1.123"
LOG_FILE = "ntp_drift_log.txt"
INTERVAL = 30 * 60  # 1800 secondi
time_counter = 8

def get_ntp_offset():
    try:
        result = subprocess.run(
            ["sudo", "ntpdate", COORDINATOR_IP],
            capture_output=True,
            text=True
        )
        output = result.stdout.split("\n")
        
        for line in output:
            if COORDINATOR_IP in line:
                parts = line.split()
                offset = float(parts[3])  # Offset (ritardo)

                error = float(parts[5])   # Errore massimo stimato
                return offset, error
    except Exception as e:
        print(f"Errore nell'esecuzione di ntpdate: {e}")
        return None, None

def log_ntp_drift():
    with open(LOG_FILE, mode="w", newline="") as csv_file:
        fieldnames = ["Timestamp", "Offset (s)", "Max Error (s)"]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        try:
            for _ in range(time_counter):
                offset, error = get_ntp_offset()
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                writer.writerow({"Timestamp": timestamp, "Offset (s)": offset, "Max Error (s)": error})
                print(f"{timestamp}, Offset: {offset:.6f} s, Max error: {error:.6f} s")

                time.sleep(INTERVAL)

        except KeyboardInterrupt:
            print("Measurement stopped from keyboard")
        finally:
            csv_file.close()

if __name__ == "__main__":
    log_ntp_drift()