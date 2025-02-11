import threading
import socket
import netifaces

BUSY = "BUSY"
READY = "READY"

MY_PC_IFACE = "Wi-Fi" # This is for test on my PC
WLAN_IFACE = 'wlan0'
ETHERNET_IFACE = 'eth0'
HAT_IFACE = 'rmnet_mhi0.1'

class SharedState:
    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(SharedState, cls).__new__(cls)
            cls.instance.lock = threading.Lock()
            cls.instance.probe_state = READY
            cls.instance.coordinator_ip = None
            cls.probe_ip = None
        return cls.instance
    
    def __init__(self):
        if self.probe_ip is None:
            self.get_probe_ip()

    def get_probe_ip(self):
        with self.lock:
            if self.probe_ip is None:
                try:
                    gateways = netifaces.gateways()
                    default_iface = gateways['default'][netifaces.AF_INET][1]
                    my_ip = netifaces.ifaddresses(default_iface)[netifaces.AF_INET][0]['addr']
                    self.probe_ip = my_ip
                    print(f"SharedState: default nic -> |{default_iface}| , my_ip -> |{my_ip}| ")
                except KeyError as k:
                    print(f"SharedState: exception in retrieve my ip -> {k} ")
                    self.probe_ip = "0.0.0.0"
            return self.probe_ip
        """
        available_interfaces = psutil.net_if_addrs().keys()
        print(f"Netcards: {available_interfaces}")
        if HAT_IFACE in available_interfaces:
            my_ip = netifaces.ifaddresses(HAT_IFACE)[netifaces.AF_INET][0]['addr']
        elif WLAN_IFACE in available_interfaces:
            my_ip = netifaces.ifaddresses(WLAN_IFACE)[netifaces.AF_INET][0]['addr']
        elif ETHERNET_IFACE in available_interfaces:
            my_ip = netifaces.ifaddresses(ETHERNET_IFACE)[netifaces.AF_INET][0]['addr']
        elif MY_PC_IFACE in available_interfaces:
            my_ip = netifaces.ifaddresses(MY_PC_IFACE)[netifaces.AF_INET][0]['addr']
        else:
            my_ip = "DA CORREGGERE"
            raise Exception(f"No network interfaces found! List -> {available_interfaces}")
        """
        return my_ip

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