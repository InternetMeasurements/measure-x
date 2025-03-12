import os
from mqttModule.mqttClient import ProbeMqttClient
from commandsDemultiplexer.commandsDemultiplexer import CommandsDemultiplexer
from iperfModule.iperfController import IperfController
from pingModule.pingController import PingController
from energyModule.energyController import EnergyController
from aoiModule.aoiController import AgeOfInformationController
from shared_resources import shared_state
from udppingModule.udppingController import UDPPingController


class Probe:
    def __init__(self, probe_id):
        self.id = probe_id
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
                                                         self.commands_demultiplexer.wait_for_set_coordinator_ip)
        
        self.udpping_controller = UDPPingController(self.mqtt_client, 
                                                    self.commands_demultiplexer.registration_handler_request,
                                                    self.commands_demultiplexer.wait_for_set_coordinator_ip)

    
    def disconnect(self):
        self.mqtt_client.disconnect()


def main():
    user_name = os.getlogin()
    if user_name == "coordinator" or user_name=="Francesco": # Trick for execute the firmware on the coordinator
        user_name = "probe1"
    probe1 = Probe(user_name)
    while True:
        command = input()
        match command:
            case "0":
                probe1.disconnect()
                break
            case _:
                continue  
    return

if __name__ == "__main__":
    main()