"""
Firmware entry point for the probe device in Measure-X.
Handles initialization, connectivity (5G or WiFi), and controller setup for all supported measurement modules.
"""

import os
import time, psutil
import subprocess, threading
import signal
import argparse
import yaml
from mqttModule.mqttClient import ProbeMqttClient
from commandsDemultiplexer.commandsDemultiplexer import CommandsDemultiplexer
from iperfModule.iperfController import IperfController
from pingModule.pingController import PingController
from energyModule.energyController import EnergyController
from aoiModule.aoiController import AgeOfInformationController
from shared_resources import SharedState, HAT_IFACE
from udppingModule.udppingController import UDPPingController
from coexModule.coexController import CoexController

class Probe:
    """
    Main class representing a probe device.
    Handles connectivity setup, controller initialization, and MQTT client management.
    """
    def __init__(self, probe_id, dbg_mode):
        """
        Initialize the probe, set up connectivity (5G or WiFi), and instantiate all controllers.
        """
        self.id = probe_id
        self.commands_demultiplexer = None
        self.waveshare_cm_thread = None
        self.waveshare_process = None
        if not dbg_mode:
            print(f"{probe_id}: 5G mode enabled. Establishing mobile connection...")
            self.waveshare_cm_thread = threading.Thread(target=self.body_start_waveshare_cm)
            self.waveshare_cm_thread.daemon = True
            self.waveshare_cm_thread.start()
            can_continue = self.waiting_for_5G_connection()
            if not can_continue:
                print(f"{probe_id}: CAN'T ESTABLISH 5G CONNECTIVITY")
                return
            
        else:
            print(f"{probe_id}: DBG mode enabled. Using WiFi...")

        # Initialize shared state and all controllers
        SharedState.get_instance() 

        self.commands_demultiplexer = CommandsDemultiplexer()
        self.mqtt_client = ProbeMqttClient(probe_id,
                                           self.commands_demultiplexer.decode_command) # The Decode Handler is triggered internally
        self.commands_demultiplexer.set_mqtt_client(self.mqtt_client)

        self.iperf_controller = IperfController(self.mqtt_client,
                                                self.commands_demultiplexer.registration_handler_request) # ENABLE THROUGHPUT FUNCTIONALITY
        
        self.ping_controller = PingController(self.mqtt_client,
                                              self.commands_demultiplexer.registration_handler_request)   # ENABLE LATENCY FUNCTIONALITY
        
        self.energy_controller = EnergyController(self.mqtt_client,
                                                  self.commands_demultiplexer.registration_handler_request) # ENABLE POWER CONSUMPTION FUNCTIONALITY
        
        self.aoi_controller = AgeOfInformationController(self.mqtt_client, 
                                                         self.commands_demultiplexer.registration_handler_request,
                                                         self.commands_demultiplexer.wait_for_set_coordinator_ip) # ENABLE AGE OF INFORMATION FUNCTIONALITY
        
        self.udpping_controller = UDPPingController(self.mqtt_client, 
                                                    self.commands_demultiplexer.registration_handler_request,
                                                    self.commands_demultiplexer.wait_for_set_coordinator_ip) # ENABLE UDP-PING based FUNCTIONALITY
        
        self.coex_controller = CoexController(self.mqtt_client,
                                              self.commands_demultiplexer.registration_handler_request)   # ENABLE COEXISTING APPLICATION FUNCTIONALITY

        
    def waiting_for_5G_connection(self):
        """
        Wait for the 5G interface to become available and up.
        Returns True if the interface is up, False otherwise.
        """
        interfaces = psutil.net_if_addrs()
        count_retry = 0
        MAX_RETRY = 5
        iface_found = False
        if (HAT_IFACE not in interfaces):
            return False
        while count_retry < MAX_RETRY:
            net_if_stats = psutil.net_if_stats()
            time.sleep(2)
            if (not net_if_stats[HAT_IFACE].isup): # If the HAT_IFACE is down...
                count_retry += 1
                print(f"{self.id}: Waiting for mobile connection ... Attemtp {count_retry} of {MAX_RETRY}")
            else:
                iface_found = True
                break
        return iface_found


    def body_start_waveshare_cm(self):
        """
        Start the Waveshare-CM process in a separate thread for 5G connectivity.
        """
        try:
            self.waveshare_process = subprocess.Popen(
                                        ['sudo', 'waveshare-CM'],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        preexec_fn=os.setsid)
            
        except Exception as e:
            print(f"{self.id}: Exception during waveshare driver execution --> {e}")



    def disconnect(self):
        """
        Disconnect the MQTT client and clean up resources.
        """
        self.mqtt_client.disconnect()

def get_probe_id_from_yaml(yaml_path="probe_config.yaml"):
    """
    Reads the probe id from a yaml configuration file.
    """
    try:
        with open(yaml_path, "r") as f:
            config = yaml.safe_load(f)
            return config.get("probe_id", None)
    except Exception as e:
        print(f"Error reading probe id from yaml: {e}")
        return None

def main():
    """
    Main entry point for the probe firmware. Handles argument parsing and probe lifecycle.
    """
    parser = argparse.ArgumentParser(description="Script to handle dbg mode")
    parser.add_argument('-dbg', action='store_true', help="Enable the debug mode.")
    args = parser.parse_args()

# VECCHIO
#    user_name = os.getlogin()
#    if user_name == "coordinator" or user_name=="Francesco": # Trick for execute the firmware also on the coordinator
#        user_name = "probe1"
#    probe = Probe(user_name, args.dbg)
    probe_id_from_yaml = get_probe_id_from_yaml()
    probe = Probe(probe_id_from_yaml, args.dbg)

    if probe.commands_demultiplexer is not  None:
        while True:
            command = input()
            match command:
                case "0":
                    probe.disconnect()
                    break
                case _:
                    continue

    if probe.waveshare_process is not None:
        try:
            print(f"{probe.id}: stopping waveshare-CM driver")
            os.killpg(os.getpgid(probe.waveshare_process.pid), signal.SIGTERM)
        except Exception as e:
            print(f"{probe.id}: Exception during stop -> {e}")
    return

if __name__ == "__main__":
    main()