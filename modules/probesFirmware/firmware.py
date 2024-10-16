from modules.probesFirmware.mqttModule.mqttClient import ProbeMqttClient

class Probe:
    def __init__(self, probe_id):
        self.id = probe_id
        self.state = None
        self.mqtt_client = ProbeMqttClient(probe_id)
    
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