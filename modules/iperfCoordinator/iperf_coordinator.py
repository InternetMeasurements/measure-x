import os
import json
from pathlib import Path
from src.modules.mqttModule.mqttClient import MqttClient

class Iperf_Coordinator:
    def __init__(self, mqtt : MqttClient):
        self.mqtt = mqtt 
        self.received_acks = set()
        self.expected_acks = set()
        self.last_client_probe = None

    def result_handler_received(self, probe_sender, result: json):
        self.store_measurement_result(probe_sender, result)
        
    def status_handler_rcvd(self, probe_sender, status : str):
        if status.__contains__("conf: OK"):
            if probe_sender in self.expected_acks:
                self.received_acks.add(probe_sender)
                print(f"iperf_coordinator: ACK received for probe -> {probe_sender}")
        else:
            print(f"iperf_coordinator: NACK received for {probe_sender} -> {status}")


    def send_probe_iperf_role(self, probe_id, role):
        if role == "Client":
            self.last_client_probe = probe_id
        self.expected_acks.add(probe_id) # Add this probe in the list from which i'm expecting an ACK
        command_role = "iperf: role=" + role
        self.mqtt.publish_command(command = command_role, probe_id = probe_id)
        
    def send_probe_iperf_start(self):
        """
        if self.expected_acks == set():
            print("iperf_coordinator: expected_acks empty")
            return

        if self.expected_acks != self.received_acks:
            print(f"iperf_coordinator: Can't iperf start. Waiting for {self.expected_acks - self.received_acks} role ACK")
            return
        """
        if self.last_client_probe is None:
            print("iperf_coordinator: Did you configured the probes first?")
            return
    
        command_iperf_start = "iperf: start"
        self.mqtt.publish_command(command = command_iperf_start, probe_id = self.last_client_probe)
        print("iperf_coordinator: iperf started on probes. Waiting for results...")

    def store_measurement_result(self, probe_sender, json_measurement: json):
        base_path = Path(__file__).parent
        probe_measurement_dir = Path(os.path.join(base_path, 'measurements', probe_sender))
        complete_measurement_path = os.path.join(base_path, probe_measurement_dir, "measure_" + str(json_measurement['measurement_id']) + ".json")
        if not probe_measurement_dir.exists():
            os.makedirs(probe_measurement_dir, exist_ok=True)
        with open(complete_measurement_path, "w") as file:
            file.write(json.dumps(json_measurement, indent=4))
        print(f"iperf_coordinator: stored result from {probe_sender} -> measure_{str(json_measurement['measurement_id'])}.json")
