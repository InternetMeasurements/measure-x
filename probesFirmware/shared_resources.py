import threading

class SharedState:
    def __init__(self):
        self.lock = threading.Lock()
        self.BUSY = "BUSY"
        self.READY = "READY"
        self.probe_state = self.READY

    def set_probe_as_ready(self) -> bool:
        with self.lock:
            self.probe_state = self.READY
            print(f"SharedState: state setted to |{self.READY}|")
            return True

    def set_probe_as_busy(self) -> bool:
        with self.lock:
            if self.probe_state == self.BUSY:
                print(f"SharedState: the probe is already busy")
                return False
            self.probe_state = self.READY
            print(f"SharedState: state setted to |{self.BUSY}|")
            return True
        
    def probe_is_ready(self) -> bool:
        with self.lock:
            return (self.probe_state == self.READY)

shared_state = SharedState() # my singleton shared