import os
import time, psutil
import subprocess, threading
import signal
import argparse
from mqttModule.mqttClient import ProbeMqttClient
from commandsDemultiplexer.commandsDemultiplexer import CommandsDemultiplexer
from iperfModule.iperfController import IperfController
from pingModule.pingController import PingController
from energyModule.energyController import EnergyController
from aoiModule.aoiController import AgeOfInformationController
from shared_resources import SharedState
from udppingModule.udppingController import UDPPingController
from coexModule.coexController import CoexController


class Probe:
    def __init__(self, probe_id, dbg_mode):
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
        
        #self.coex_controller.scapy_test()
        
    def waiting_for_5G_connection(self):
        interfaces = psutil.net_if_addrs()
        count_retry = 0
        MAX_RETRY = 5
        iface_found = False
        while count_retry < MAX_RETRY:
            time.sleep(2)
            if ("rmnet_mhi0.1" not in interfaces):
                print(f"{self.id}: Waiting for mobile connection ... Attemtp {count_retry} of {MAX_RETRY}")
                count_retry += 1
            else:
                iface_found = True
                break
        return iface_found

    
    def disconnect(self):
        self.mqtt_client.disconnect()
    
    def body_start_waveshare_cm(self):
        try:
            # Esegui il comando con cattura dell'output (senza timeout)
            self.waveshare_process = subprocess.Popen(
                                        ['sudo', 'waveshare-CM'],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        preexec_fn=os.setsid)
            
            # Se il comando è stato eseguito correttamente
            print(f"Comando eseguito correttamente")
            
        except subprocess.CalledProcessError as e:
            print(f"Errore durante l'esecuzione del processo: {e.stderr}")
        except FileNotFoundError as e:
            print(f"Errore: il comando non è stato trovato: {e}")
        except Exception as e:
            print(f"Si è verificato un errore imprevisto: {e}")


def main():
    parser = argparse.ArgumentParser(description="Script to handle dbg mode")
    parser.add_argument('-dbg', action='store_true', help="Enable the debug mode.")
    args = parser.parse_args()

    user_name = os.getlogin()
    if user_name == "coordinator" or user_name=="Francesco": # Trick for execute the firmware also on the coordinator
        user_name = "probe1"
    probe = Probe(user_name, args.dbg)
    if probe.commands_demultiplexer is None:
        return
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
            print(f"{user_name}: killing waveshare-CM thread")
            os.killpg(os.getpgid(probe.waveshare_process.pid), signal.SIGTERM)
        except Exception as e:
            print(f"{probe.id}: Exception during kill -> {e}")
    return

if __name__ == "__main__":
    main()