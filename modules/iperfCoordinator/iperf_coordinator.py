import os
import json
import yaml
from pathlib import Path
from src.modules.mqttModule.mqttClient import MqttClient

class Iperf_Coordinator:
    def __init__(self, mqtt : MqttClient):
        self.mqtt = mqtt 
        self.received_acks = set()
        self.expected_acks = set()
        self.probes_configurations_dir = 'probes_configurations'
        self.last_client_probe = None
        self.probes_servers_ip = {}
        self.probes_servers_port = {}

    def result_handler_received(self, probe_sender, result: json):
        self.store_measurement_result(probe_sender, result)
        
    def status_handler_received(self, probe_sender, status : json):
        command = status["command"]
        match command:
            case "conf":
                if "reason" not in status: # If true, then this status is an ACK
                    if ("ip" in status) and ("port" in status):
                        probe_ip = status["ip"]
                        probe_port = status["port"]
                        self.probes_ip[probe_sender] = probe_ip
                        self.probes_servers_port[probe_sender] = probe_port
                    print(f"Iperf_Coordinator: probe |{probe_sender}|->|{probe_ip}|->|{command}|->ACK")
                else: # else, this is an NACK
                    reason = status['reason']
                    print(f"Iperf_Coordinator: probe |{probe_sender}|->|{command}|->NACK, reason->{reason}")
            case _:
                print(f"Iperf_Coordinator: status message not handled-> |{command}|")

    def get_json_from_probe_yaml(self, probes_configurations_path) -> json:
        json_probe_config = {}
        with open(probes_configurations_path, "r") as file:
            config = yaml.safe_load(file)
            json_probe_config = {
                "destination_server_ip": config['destination_server_ip'],
                "destination_server_port": int(config['destination_server_port']),
                "transport_protocol": True if (config['transport_protocol'] == "TCP") else False,
                "parallel_connections": int(config['parallel_connections']),
                "result_measurement_filename": config['result_measurement_filename'],
                "reverse": config['reverse'],
                "verbose": False,
                "total_repetition": int(config['total_repetition']),
            }
        return json_probe_config

    def send_probe_iperf_configuration(self, probe_id, role, dest_probe = None): # Tramite il probe_id, devi caricare il file YAML per quella probes
        json_config = {}
        if role == "Client":
            base_path = Path(__file__).parent
            probes_configurations_path = Path(os.path.join(base_path, self.probes_configurations_dir, "configToBeClient.yaml"))
            if probes_configurations_path.exists():
                if (dest_probe not in self.probes_servers_ip) or (dest_probe not in self.probes_servers_port):
                    print(f"Iperf_Coordinator: configure the Probe Server first")
                    return
                json_config = self.get_json_from_probe_yaml(probes_configurations_path)
                json_config['destination_server_ip'] = self.probes_servers_ip[dest_probe]
                json_config['destination_server_port'] = self.probes_servers_port[dest_probe]
                self.last_client_probe = probe_id
            else:
                print(f"Iperf_Coordinator: File not found->|{probes_configurations_path}|")
        else:
            # Questo json_config è quello di default per il Server.
            json_config = {
                "listen_port": 5201,
                "verbose": True
            }
        self.expected_acks.add(probe_id) # Add this probe in the list from which i'm expecting an ACK
        json_command = {
            "handler": 'iperf',
            "command": "conf",
            "payload": json_config
        }
        self.mqtt.publish_on_command_topic(probe_id=probe_id, complete_command=json.dumps(json_command))
        
    def send_probe_iperf_start(self):
        if self.expected_acks == set():
            print("iperf_coordinator: expected_acks empty")
            return

        if self.expected_acks != self.received_acks:
            print(f"iperf_coordinator: Can't iperf start. Waiting for {self.expected_acks - self.received_acks} role ACK")
            return

        if self.last_client_probe is None:
            print("iperf_coordinator: Did you configured the probes first?")
            return
        
        json_iperf_start = {
            "handler": "iperf",
            "command": "start",
            "payload": {}
        }
    
        self.mqtt.publish_on_command_topic(probe_id = self.last_client_probe, command = json.dumps(json_iperf_start))
        print("Iperf_Coordinator: iperf started on probes. Waiting for results...")

    def store_measurement_result(self, probe_sender, json_measurement: json):
        base_path = Path(__file__).parent
        probe_measurement_dir = Path(os.path.join(base_path, 'measurements', probe_sender))
        complete_measurement_path = os.path.join(base_path, probe_measurement_dir, "measure_" + str(json_measurement['measurement_id']) + ".json")
        if not probe_measurement_dir.exists():
            os.makedirs(probe_measurement_dir, exist_ok=True)
        with open(complete_measurement_path, "w") as file:
            file.write(json.dumps(json_measurement, indent=4))
        print(f"Iperf_Coordinator: stored result from {probe_sender} -> measure_{str(json_measurement['measurement_id'])}.json")
