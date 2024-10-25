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
        self.probes_server_ip = {}
        self.probes_server_port = {}

    def result_handler_received(self, probe_sender, result: json):
        self.print_summary_result(measurement_result = result)
        self.store_measurement_result(probe_sender, result)
        
    def status_handler_received(self, probe_sender, type, payload : json):
        match type:
            case "ACK":
                command_executed_on_probe = payload["command"]
                match command_executed_on_probe:
                    case "conf":
                        if ("ip" in payload) and ("port" in payload):
                            probe_ip = payload["ip"]
                            probe_port = payload["port"]
                            self.probes_server_ip[probe_sender] = probe_ip
                            self.probes_server_port[probe_sender] = probe_port
                            print(f"Iperf_Coordinator: probe |{probe_sender}|->|{probe_ip}|->|{probe_port}|->ACK")
                        # the else statement, means that the ACK is sent from the client
                        self.received_acks.add(probe_sender)
                    case "stop":
                         print(f"Iperf_Coordinator: probe |{probe_sender}|-> Iperf-server stopped -> ACK")
                    case _:
                        print(f"ACK received for unkonwn iperf command -> {command_executed_on_probe}")
            case "NACK":
                command_failed_on_probe = payload["command"]
                reason = payload['reason']
                print(f"Iperf_Coordinator: probe |{probe_sender}|->|{command_failed_on_probe}|->NACK, reason->{reason}")
            case "result":
                measurement_result = payload
                print(f"measurement_result: {measurement_result}")
            case _:
                print(f"Iperf_Coordinator: received unkown type message -> |{type}|")

    def get_json_from_probe_yaml(self, probes_configurations_path) -> json:
        json_probe_config = {}
        with open(probes_configurations_path, "r") as file:
            iperf_client_config = yaml.safe_load(file)['iperf_client']
            json_probe_config = {
                "transport_protocol": iperf_client_config['transport_protocol'],
                "parallel_connections": int(iperf_client_config['parallel_connections']),
                "result_measurement_filename": iperf_client_config['result_measurement_filename'],
                "reverse": iperf_client_config['reverse'],
                "verbose": False,
                "total_repetition": int(iperf_client_config['total_repetition']),
            }
        return json_probe_config

    def send_probe_iperf_configuration(self, probe_id, role, dest_probe = None): # Tramite il probe_id, devi caricare il file YAML per quella probes
        json_config = {}
        if role == "Client": # Preparing the config for the iperf-client
            base_path = Path(__file__).parent
            probes_configurations_path = Path(os.path.join(base_path, self.probes_configurations_dir, "configToBeClient.yaml"))
            if probes_configurations_path.exists():
                if (dest_probe not in self.probes_server_ip) or (dest_probe not in self.probes_server_port):
                    print(f"Iperf_Coordinator: configure the Probe Server first")
                    return
                json_config = self.get_json_from_probe_yaml(probes_configurations_path)
                json_config['role'] = "Client"
                json_config['save_result_on_flash'] = True
                json_config['destination_server_ip'] = self.probes_server_ip[dest_probe]
                json_config['destination_server_port'] = self.probes_server_port[dest_probe]
                self.last_client_probe = probe_id
            else:
                print(f"Iperf_Coordinator: File not found->|{probes_configurations_path}|")
        else: # Preparing the config for the iperf-server
            json_config = {
                "role": "Server",
                "listen_port": 5201,
                "verbose": True
            }
        json_command = {
            "handler": 'iperf',
            "command": "conf",
            "payload": json_config
        }
        self.expected_acks.add(probe_id) # Add this probe in the list from which i'm expecting to receive an ACK
        self.mqtt.publish_on_command_topic(probe_id=probe_id, complete_command=json.dumps(json_command))
        
    def send_probe_iperf_start(self):
        if self.expected_acks == set():
            print("iperf_coordinator: expected_acks empty")
            return

        if self.expected_acks != self.received_acks:
            print(f"iperf_coordinator: Can't iperf start. Waiting for {self.expected_acks - self.received_acks} role ACK")
            return

        if self.last_client_probe is None:
            print("iperf_coordinator: Did you configured the client probe first?")
            return
        
        json_iperf_start = {
            "handler": "iperf",
            "command": "start",
            "payload": {}
        }
    
        self.mqtt.publish_on_command_topic(probe_id = self.last_client_probe, complete_command = json.dumps(json_iperf_start))
        print("Iperf_Coordinator: iperf started on probes. Waiting for results...")
    
    def send_probe_iperf_stop(self, probe_id):
        json_iperf_stop = {
            "handler": "iperf",
            "command": "stop",
            "payload": {}
        }
        self.mqtt.publish_on_command_topic(probe_id = probe_id, complete_command = json.dumps(json_iperf_stop))


    def store_measurement_result(self, probe_sender, json_measurement: json):
        base_path = Path(__file__).parent
        probe_measurement_dir = Path(os.path.join(base_path, 'measurements', probe_sender))
        complete_measurement_path = os.path.join(base_path, probe_measurement_dir, "measure_" + str(json_measurement['measurement_id']) + ".json")
        if not probe_measurement_dir.exists():
            os.makedirs(probe_measurement_dir, exist_ok=True)
        with open(complete_measurement_path, "w") as file:
            file.write(json.dumps(json_measurement, indent=4))
        print(f"Iperf_Coordinator: stored result from {probe_sender} -> measure_{str(json_measurement['measurement_id'])}.json")

    def print_summary_result(self, measurement_result):
        
        start_timestamp = measurement_result["start_timestamp"]
        measurement_id = measurement_result["measurement_id"]
        source_ip = measurement_result["source_ip"]
        destination_ip = measurement_result["destination_ip"]
        bytes_received = measurement_result["bytes_received"]
        duration = measurement_result["duration"]
        avg_speed = measurement_result["avg_speed"]

        print("\n****************** SUMMARY ******************")
        print(f"Timestamp: {start_timestamp}")
        print(f"Measurement ID: {measurement_id}")
        print(f"IP sorgente: {source_ip}")
        print(f"IP destinatario: {destination_ip}")
        print(f"Velocità trasferimento {avg_speed} bits/s")
        print(f"Quantità di byte ricevuti: {bytes_received}")
        print(f"Durata misurazione: {duration} secondi\n")
        