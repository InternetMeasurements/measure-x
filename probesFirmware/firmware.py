from src.probesFirmware.mqttModule.mqttClient import ProbeMqttClient
from src.probesFirmware.commandsMultiplexer.commandsMultiplexer import CommandsMultiplexer
from src.probesFirmware.iperfClient.iperfController import IperfController
from src.probesFirmware.latencyModule.pingController import PingController

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
    probe1 = Probe("probe2")
    while True:
        command = input()
        if(command == '0'):
            probe1.disconnect()
            break
    return

if __name__ == "__main__":
    main()