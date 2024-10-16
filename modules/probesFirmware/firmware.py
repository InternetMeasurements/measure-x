from src.modules.probesFirmware.mqttModule.mqttClient import ProbeMqttClient
from src.modules.probesFirmware.commandsExecutor.commandsExecutor import CommandsExecutor

class Probe:
    def __init__(self, probe_id):
        self.id = probe_id
        self.state = None
        self.role = None
        self.command_executor = CommandsExecutor()
        self.mqtt_client = ProbeMqttClient(probe_id, self.command_executor.decode_command) # The Decode Handler is triggered internally

    def check_for_ready(self):
        return self.state
    
    def disconnect(self):
        self.mqtt_client.disconnect()

    
    

def main():
    probe1 = Probe("probe1")
    probe2 = Probe("probe2")
    while True:
        command = input()
        if(command == '0'):
            probe1.disconnect()
            probe2.disconnect()
            break
    return

if __name__ == "__main__":
    main()