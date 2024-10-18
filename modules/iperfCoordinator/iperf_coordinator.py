from src.modules.mqttModule.mqttClient import MqttClient

class Iperf_Coordinator:
    def __init__(self, mqtt : MqttClient):
        self.mqtt = mqtt 
        self.pending_acks = set()
        self.expected_acks = set()

    def iperf_msg_received(self, probe_sender, msg : str):
        if msg.__contains__("OK"):
            if probe_sender in self.expected_acks:
                self.pending_acks.add(probe_sender)
                print(f"iperf_coordinator: ACK received for probe -> {probe_sender}")
        else:
            print(f"iperf_coordinator: NOT OK -> {msg}")

    def send_probe_iperf_role(self, probe_id, role):
        self.expected_acks.add(probe_id) # Add this probe in the list from which i'm expecting an ACK
        command_role = "iperf: role=" + role
        self.mqtt.publish_command(command = command_role, probe_id = probe_id)
        
    def send_probe_iperf_start(self, probe_id):
        if self.expected_acks == {}:
            print("iperf_coordinator: expected_acks empty")
            return

        if self.expected_acks != self.pending_acks:
            print(f"iperf_coordinator: Can't iperf start. Waiting for {self.expected_acks - self.pending_acks} role ACK")
            return
        
        command_iperf_start = "iperf: start"
        self.mqtt.publish_command(command = command_iperf_start, probe_id = probe_id)
        print("iperf_coordinator: iperf started on probes. Waiting for results...")

