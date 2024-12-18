import os
import json
import yaml
import time
from pathlib import Path
from modules.mqttModule.mqtt_client import Mqtt_Client
from bson import ObjectId
from modules.mongoModule.mongoDB import MongoDB, SECONDS_OLD_MEASUREMENT
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from modules.mongoModule.models.iperf_result_model_mongo import IperfResultModelMongo

class Iperf_Coordinator:

    def __init__(self, mqtt : Mqtt_Client, registration_handler_status, registration_handler_result, mongo_db : MongoDB):
        self.mqtt = mqtt 
        self.received_acks = set()
        self.expected_acks = set()
        self.probes_configurations_dir = 'probes_configurations'
        self.last_client_probe = None
        self.probes_server_port = {}
        self.mongo_db = mongo_db
        self.last_mongo_measurement = None # In this attribute, i save the measurement before store it in mongoDB

        # Requests to commands_multiplexer
        registration_response = registration_handler_status(
            interested_status = "iperf",
            handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"Iperf_Coordinator: registered handler for status -> iperf")
        else:
            print(f"Iperf_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer
        registration_response = registration_handler_result(
            interested_result = "iperf",
            handler = self.handler_received_result)
        if registration_response == "OK" :
            print(f"Iperf_Coordinator: registered handler for result -> iperf")
        else:
            print(f"Iperf_Coordinator: registration handler failed. Reason -> {registration_response}")


    def handler_received_result(self, probe_sender, result: json):
        if ((time.time() - result["start_timestamp"]) < SECONDS_OLD_MEASUREMENT):
            self.store_measurement_result(result)
            self.print_summary_result(measurement_result = result)
        else: #Volendo posso anche evitare questo settaggio, perchè ci penserà il thread periodico
            #if self.mongo_db.set_measurement_as_failed_by_id(result['measure_reference']):
            print(f"Iperf_Coordinator: ignored result. Reason: expired measurement -> {result['measure_reference']}")

        
    def handler_received_status(self, probe_sender, type, payload : json):
        match type:
            case "ACK":
                command_executed_on_probe = payload["command"]
                match command_executed_on_probe:
                    case "conf":
                        if "port" in payload: # if the 'port' key is in the payload, then it's the ACK comes from iperf-server
                            probe_port = payload["port"]
                            self.probes_server_port[probe_sender] = probe_port
                            print(f"Iperf_Coordinator: probe |{probe_sender}|->|Listening port: {probe_port}|->|ACK|")
                        # the else statement, means that the ACK is sent from the client.
                        else:
                            print(f"Iperf_Coordinator: probe |{probe_sender}|->|conf|->|ACK|")
                        # ↓ In any case, i add the probe_id to the probes from which i received its conf-ACK
                        self.received_acks.add(probe_sender)
                    case "stop":
                         print(f"Iperf_Coordinator: probe |{probe_sender}|->|Iperf stopped|->|ACK|")
                         self.probes_server_port.pop(probe_sender, None)
                    case _:
                        print(f"ACK received for unkonwn iperf command -> {command_executed_on_probe}")
            case "NACK":
                command_failed_on_probe = payload["command"]
                reason = payload['reason']
                print(f"Iperf_Coordinator: probe |{probe_sender}|->|{command_failed_on_probe}|->|NACK|, reason --> {reason}")
                match command_failed_on_probe:
                    case "start":
                        print("comando fallito start")
                        if self.mongo_db.set_measurement_as_failed_by_id(measurement_id = self.last_mongo_measurement._id):
                            print(f"Iperf_Coordinator: measurement |{self.last_mongo_measurement._id}| setted as failed")

            case _:
                print(f"Iperf_Coordinator: received unkown type message -> |{type}|")


    def send_probe_iperf_configuration(self, probe_id, role, source_probe_ip = None, dest_probe = None, dest_probe_ip = None): # Tramite il probe_id, devi caricare il file YAML per quella probes
        json_config = {}
        if role == "Client": # Preparing the config for the iperf-client
            base_path = Path(__file__).parent
            probes_configurations_path = Path(os.path.join(base_path, self.probes_configurations_dir, "configToBeClient.yaml"))
            if probes_configurations_path.exists():
                if (dest_probe_ip is None) or (dest_probe not in self.probes_server_port):
                    print(f"Iperf_Coordinator: configure the Probe Server first")
                    return
                
                # ↓ I'm JUST getting ready to store it in Mongo.
                self.last_mongo_measurement = MeasurementModelMongo(
                    description = "Throughupt measure with iperf tool",
                    type = "Throughput",
                    source_probe = probe_id,
                    dest_probe = dest_probe,
                    source_probe_ip = source_probe_ip,
                    dest_probe_ip = dest_probe_ip)
                
                json_config = self.get_json_from_probe_yaml(probes_configurations_path)
                json_config['role'] = "Client"
                json_config['measurement_id'] = None # REMEMBER: --> Only at the start command, the measurment_id is sent to the probe!
                json_config['destination_server_ip'] = dest_probe_ip
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
        
        measurement_id = self.mongo_db.insert_measurement(self.last_mongo_measurement)
        self.last_mongo_measurement._id = measurement_id
        if measurement_id is None:
            print("Iperf_Coordinator: Can't send start! Error while inserting measurement iperf in mongo")
            return

        json_iperf_start = {
            "handler": "iperf",
            "command": "start",
            "payload": {
                "measurement_id": str(measurement_id)
            }
        }
        self.mqtt.publish_on_command_topic(probe_id = self.last_client_probe, complete_command = json.dumps(json_iperf_start))

    
    def send_probe_iperf_stop(self, probe_id):
        json_iperf_stop = {
            "handler": "iperf",
            "command": "stop",
            "payload": {}
        }
        self.mqtt.publish_on_command_topic(probe_id = probe_id, complete_command = json.dumps(json_iperf_stop))


    def store_measurement_result(self, result : json):
        mongo_result = IperfResultModelMongo(
            measure_reference = ObjectId(result["measure_reference"]),
            repetition_number = result["repetition_number"],
            start_timestamp = result["start_timestamp"],
            transport_protocol = result["transport_protocol"],
            source_ip = result["source_ip"],
            source_port = result["source_port"],
            destination_ip = result["destination_ip"],
            destination_port = result["destination_port"],
            bytes_received = result["bytes_received"],
            duration = result["duration"],
            avg_speed = result["avg_speed"]
        )
        result_id = str(self.mongo_db.insert_iperf_result(result=mongo_result))
        if result_id is not None:
            print(f"Iperf_Coordinator: result |{result_id}| stored in db")
        else:
            print(f"Iperf_Coordinator: error while storing result |{result_id}|")

        last_result = result["last_result"]
        if last_result: # if this result is the last, then i must set the stop timestamp on the measurment collection in Mongo
            if self.mongo_db.set_measurement_as_completed(result["measure_reference"]):
                print(f"Iperf_Coordinator: measurement |{result['measure_reference']}| completed ")
        else:
            print("Iperf_Coordinator: result not last")


    def print_summary_result(self, measurement_result : json):
        start_timestamp = measurement_result["start_timestamp"]
        repetition_number = measurement_result["repetition_number"]
        measure_reference = measurement_result["measure_reference"]
        source_ip = measurement_result["source_ip"]
        transport_protocol = measurement_result["transport_protocol"]
        destination_ip = measurement_result["destination_ip"]
        bytes_received = measurement_result["bytes_received"]
        duration = measurement_result["duration"]
        avg_speed = measurement_result["avg_speed"]

        print("\n****************** SUMMARY ******************")
        print(f"Timestamp: {start_timestamp}")
        print(f"Repetition number: {repetition_number}")
        print(f"Measurement reference: {measure_reference}")
        print(f"Transport protocol: {transport_protocol}")
        print(f"IP sorgente: {source_ip}")
        print(f"IP destinatario: {destination_ip}")
        print(f"Velocità trasferimento {avg_speed} bits/s")
        print(f"Quantità di byte ricevuti: {bytes_received}")
        print(f"Durata risultato: {duration} secondi\n")

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
                "save_result_on_flash": iperf_client_config['save_result_on_flash']
            }
        return json_probe_config

    """
    def store_measurement_result(self, probe_sender, json_measurement: json):
        base_path = Path(__file__).parent
        probe_measurement_dir = Path(os.path.join(base_path, 'measurements', probe_sender))
        complete_measurement_path = os.path.join(base_path, probe_measurement_dir, "measure_" + str(json_measurement['measurement_id']) + ".json")
        if not probe_measurement_dir.exists():
            os.makedirs(probe_measurement_dir, exist_ok=True)
        with open(complete_measurement_path, "w") as file:
            file.write(json.dumps(json_measurement, indent=4))
        print(f"Iperf_Coordinator: stored result from {probe_sender} -> measure_{str(json_measurement['measurement_id'])}.json")

    def get_last_measurement_id(self, probe_id):
        #It returns the id that can be used as Current-Measurement-ID
        base_path = Path(__file__).parent
        output_path = os.path.join(base_path, "measurements", probe_id)
        
        file_list = os.listdir(output_path)
        file_list = [measurement_file for measurement_file in file_list if measurement_file.startswith("measure_")]

        if not file_list:
            return 0
        
        sorted_list = sorted(file_list, key=lambda x: int(x.split('_')[1].split('.')[0]))
        last_element_ID = int(sorted_list[-1].split('_')[-1].split(".")[0])
        return last_element_ID + 1
    """
        