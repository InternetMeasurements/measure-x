import threading
import socket
import netifaces
import scapy.all as scapy

BUSY = "BUSY"
READY = "READY"

# MY_PC_IFACE = "Wi-Fi" # This is for test on my PC
# WLAN_IFACE = 'wlan0'
ETHERNET_IFACE = 'eth0'
HAT_IFACE = 'rmnet_mhi0.1'

class SharedState:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SharedState, cls).__new__(cls)
            cls._instance.lock = threading.Lock()
            cls._instance.probe_state = READY
            cls._instance.coordinator_ip = None
            cls._instance.default_nic_name = None
            cls._instance.probe_ip = None
            cls._instance.probe_mac = None
            cls._instance.probe_ip_for_clock_sync = None
        return cls._instance
    
    def __init__(self):
        if self.probe_ip is None:
            self.get_probe_ip()
            self.get_probe_mac()
            self.get_probe_ip_for_clock_sync()

    def get_probe_ip(self):
        with self.lock:
            if self.probe_ip is None:
                try:
                    gateways = netifaces.gateways()
                    default_iface = gateways['default'][netifaces.AF_INET][1]
                    self.default_nic_name = default_iface
                    my_ip = netifaces.ifaddresses(default_iface)[netifaces.AF_INET][0]['addr']
                    self.probe_ip = my_ip
                    print(f"SharedState: default nic -> |{default_iface}| , my_ip -> |{my_ip}| ")
                except KeyError as k:
                    print(f"SharedState: exception in retrieve my ip -> {k} ")
                    self.probe_ip = "0.0.0.0"
            return self.probe_ip
    
    def get_probe_mac(self):
        with self.lock:
            if self.probe_mac is None:
                try:
                    """
                    gateways = netifaces.gateways()
                    gateway_ip = gateways['default'][netifaces.AF_INET][0]
                    print(f"GATEWAY IP -> {gateway_ip}") # DBG FOR FINDING GATWAY MAC

                    default_iface = gateways['default'][netifaces.AF_INET][1]
                    self.default_nic_name = default_iface
                    my_mac = netifaces.ifaddresses(default_iface)[netifaces.AF_LINK][0]['addr']

                    arp_res = scapy.arping(gateway_ip, verbose=False)[0]
                    gateway_mac = arp_res[0][1].hwsrc if arp_res else None # Per adesso lascio stare. Comunque le probe devono informare il coordinator del MAC del loro gateway. Leggi tesi se ti dimentichi perchè!

                    print(f"GATEWAY MAC -> {gateway_mac}")

                    print(f"SharedState: default nic -> |{default_iface}| , my_mac -> |{my_mac}| ")
                    self.probe_mac = my_mac
                    """
                    gateways = netifaces.gateways()
                    default_iface = gateways['default'][netifaces.AF_INET][1]
                    self.default_nic_name = default_iface
                    my_mac = netifaces.ifaddresses(default_iface)[netifaces.AF_LINK][0]['addr']
                    print(f"SharedState: default nic -> |{default_iface}| , my_mac -> |{my_mac}| ")
                    self.probe_mac = my_mac
                except KeyError as k:
                    print(f"SharedState: exception in retrieve my mac -> {k}")
                    self.probe_mac = "ff:ff:ff:ff:ff:ff"
            return self.probe_mac

    def get_probe_ip_for_clock_sync(self):
        with self.lock:
            if (self.probe_ip_for_clock_sync is None) or (self.probe_ip_for_clock_sync == "0.0.0.0"):
                try:
                    my_ip_for_sync = netifaces.ifaddresses(ETHERNET_IFACE)[netifaces.AF_INET][0]['addr'] # SCOMMENTA QUANDO ESEGUI SU PROBE -> 18/03/2025
                    #my_ip_for_sync = "DEBUG"
                    self.probe_ip_for_clock_sync = my_ip_for_sync
                    print(f"SharedState: my ip for clock sync -> |{self.probe_ip_for_clock_sync}|")
                except Exception as k:
                    print(f"SharedState: exception in retrieve my ip for sync -> {k} ")
                    self.probe_ip_for_clock_sync = "0.0.0.0"
            return self.probe_ip_for_clock_sync
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

    @staticmethod
    def get_instance():
        if SharedState._instance is None:
            SharedState._instance = SharedState()
        return SharedState._instance
#shared_state = SharedState() # my singleton shared