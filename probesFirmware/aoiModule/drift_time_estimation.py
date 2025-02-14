import subprocess
import time
from datetime import datetime

COORDINATOR_IP = "192.168.1.123"
LOG_FILE = "ntp_drift_log.txt"
INTERVAL = 30 * 60  # 1800 secondi
time_counter = 8

def get_ntp_offset():
    """Esegue ntpdate e restituisce offset e errore massimo."""
    try:
        result = subprocess.run(
            ["sudo", "ntpdate", "-q", COORDINATOR_IP],
            capture_output=True,
            text=True
        )
        output = result.stdout.split("\n")
        
        for line in output:
            if COORDINATOR_IP in line:
                parts = line.split()
                offset = float(parts[3])  # Offset (ritardo)
                error = float(parts[4])   # Errore massimo stimato
                return offset, error
    except Exception as e:
        print(f"Errore nell'esecuzione di ntpdate: {e}")
        return None, None

def log_ntp_drift():
    global time_counter
    with open(LOG_FILE, "a") as file:
        counter = 0
        while counter < time_counter:
            offset, error = get_ntp_offset()
            if offset is not None and error is not None:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_entry = f"{timestamp}, Offset: {offset:.6f} s, Max error: {error:.6f} s\n"
                file.write(log_entry)
                print(log_entry.strip())

            time.sleep(INTERVAL)
            counter += 1

if __name__ == "__main__":
    log_ntp_drift()
    print("END")