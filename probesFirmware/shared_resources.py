import threading

BUSY = "BUSY"
READY = "READY"

class SharedState:
    def __init__(self):
        self.lock = threading.Lock()
        self.probe_state = READY

    def set_probe_as_ready(self) -> bool:
        with self.lock:
            self.probe_state = READY
            print(f"SharedState: state setted to |{READY}|")
            return True

    def set_probe_as_busy(self) -> bool:
        with self.lock:
            if self.probe_state == BUSY:
                print(f"SharedState: the probe is already busy")
                return False
            self.probe_state = BUSY
            print(f"SharedState: state setted to |{BUSY}|")
            return True
        
    def probe_is_ready(self) -> bool:
        with self.lock:
            return (self.probe_state == READY)

shared_state = SharedState() # my singleton shared