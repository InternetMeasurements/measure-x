import threading

BUSY = "BUSY"
READY = "READY"

class SharedState:
    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(SharedState, cls).__new__(cls)
            cls.instance.lock = threading.Lock()
            cls.instance.probe_state = READY
            cls.instance.coordinator_ip = None
        return cls.instance

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
        
    
    def set_coordinator_ip(self, coordinator_ip):
        with self.lock:
            if (self.coordinator_ip is None):
                self.coordinator_ip = coordinator_ip
                print(f"SharedState: setted coordinator ip -> {self.coordinator_ip}")

    def get_coordinator_ip(self):
        with self.lock:
            return self.coordinator_ip


shared_state = SharedState() # my singleton shared