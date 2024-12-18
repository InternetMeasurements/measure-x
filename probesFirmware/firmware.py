import os
from mqttModule.mqttClient import ProbeMqttClient
from commandsMultiplexer.commandsMultiplexer import CommandsMultiplexer
from iperfModule.iperfController import IperfController
from pingModule.pingController import PingController



class Probe:
    def __init__(self, probe_id):
        self.id = probe_id
        self.state = None
        self.commands_multiplexer = CommandsMultiplexer()
        self.mqtt_client = ProbeMqttClient(probe_id,
                                           self.commands_multiplexer.decode_command) # The Decode Handler is triggered internally
        self.iperf_controller = IperfController(self.mqtt_client,
                                                self.commands_multiplexer.registration_handler_request) # ENABLE THROUGHPUT FUNCTIONALITY
        self.ping_controller = PingController(self.mqtt_client,
                                              self.commands_multiplexer.registration_handler_request)   # ENABLE LATENCY FUNCTIONALITY
        
        
    def check_for_ready(self):
        return self.state
    
    def disconnect(self):
        self.mqtt_client.disconnect()


def main():
    user_name = os.getlogin()
    if user_name == "Francesco":
        user_name = "probe4"
    probe1 = Probe(user_name)
    while True:
        command = input()
        match command:
            case "0":
                probe1.disconnect()
                break
            case "1":
                probe1.mqtt_client.publish_probe_state(state="ONLINE")
            case _:
                continue  
    return

if __name__ == "__main__":
    main()