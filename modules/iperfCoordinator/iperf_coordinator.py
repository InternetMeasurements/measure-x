import os
import json
import yaml
import time
import threading
from pathlib import Path
from modules.mqttModule.mqtt_client import Mqtt_Client
from bson import ObjectId
from modules.mongoModule.mongoDB import MongoDB, SECONDS_OLD_MEASUREMENT
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from modules.mongoModule.models.iperf_result_model_mongo import IperfResultModelMongo

class Iperf_Coordinator:

    def __init__(self, mqtt : Mqtt_Client, registration_handler_status, registration_handler_result, registration_measure_preparer, mongo_db : MongoDB):
        self.mqtt = mqtt 
        self.probes_configurations_dir = 'probes_configurations'
        self.probes_server_port = {}
        self.mongo_db = mongo_db
        self.queued_measurements = {}
        self.events_received_server_ack = {}
        self.events_received_client_ack = {}

        # Requests to commands_multiplexer: handler STATUS registration
        registration_response = registration_handler_status(
            interested_status = "iperf",
            handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"Iperf_Coordinator: registered handler for status -> iperf")
        else:
            print(f"Iperf_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Handler RESULT registration
        registration_response = registration_handler_result(
            interested_result = "iperf",
            handler = self.handler_received_result)
        if registration_response == "OK" :
            print(f"Iperf_Coordinator: registered handler for result -> iperf")
        else:
            print(f"Iperf_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Probes-Preparer registration
        registration_response = registration_measure_preparer(
            interested_measurement_type = "iperf",
            preparer = self.probes_preparer_to_measurements)
        if registration_response == "OK" :
            print(f"Iperf_Coordinator: registered prepaper for measurements type -> iperf")
        else:
            print(f"Iperf_Coordinator: registration preparer failed. Reason -> {registration_response}")


    def handler_received_result(self, probe_sender, result: json):
        if ((time.time() - result["start_timestamp"]) < SECONDS_OLD_MEASUREMENT):
            self.store_measurement_result(result)
            #self.print_summary_result(measurement_result = result)
        else: #Volendo posso anche evitare questo settaggio, perchè ci penserà il thread periodico
            #if self.mongo_db.set_measurement_as_failed_by_id(result['msm_id']):
            print(f"Iperf_Coordinator: ignored result. Reason: expired measurement -> {result['msm_id']}")

        
    def handler_received_status(self, probe_sender, type, payload : json):
        match type:
            case "ACK":
                command_executed_on_probe = payload["command"]
                match command_executed_on_probe:
                    case "conf":
                        measurement_id = payload["measurement_id"]
                        if "port" in payload: # if the 'port' key is in the payload, then it's the ACK comes from iperf-server
                            probe_port = payload["port"]
                            self.probes_server_port[probe_sender] = probe_port
                            print(f"Iperf_Coordinator: probe |{probe_sender}|->|Listening port: {probe_port}|->|ACK|")
                            self.events_received_server_ack[measurement_id][1] = "OK"
                            self.events_received_server_ack[measurement_id][0].set() # Set the event ACK RECEIVER FROM SERVER
                        # the else statement, means that the ACK is sent from the client.
                        else:
                            self.events_received_client_ack[measurement_id][1] = "OK"
                            self.events_received_client_ack[measurement_id][0].set()
                            print(f"Iperf_Coordinator: probe |{probe_sender}|->|conf|-> client |ACK|")
                    case "stop":
                         print(f"Iperf_Coordinator: probe |{probe_sender}|->|Iperf stopped|->|ACK|")
                         self.probes_server_port.pop(probe_sender, None)
                    case _:
                        print(f"ACK received for unkonwn iperf command -> {command_executed_on_probe}")
            case "NACK":
                command_failed_on_probe = payload["command"]
                reason = payload['reason']
                measurement_id = payload["measurement_id"] if ('measurement_id' in payload) else None
                role_conf_failed = payload["role"] if ('role' in payload) else None
                print(f"Iperf_Coordinator: probe |{probe_sender}|->|{command_failed_on_probe}|->|NACK|, reason_payload --> {reason}, measure --> {measurement_id}")
                match command_failed_on_probe:
                    case "start":
                        print("comando fallito start")
                        if self.mongo_db.set_measurement_as_failed_by_id(measurement_id = measurement_id):
                            print(f"Iperf_Coordinator: measurement |{measurement_id}| setted as failed")
                        if role_conf_failed == "Client":
                            if measurement_id is not None: # I must stop the iperf server on the probe
                                self.send_probe_iperf_stop(self.queued_measurements[measurement_id].dest_probe, measurement_id)
                    case "conf":
                        if role_conf_failed == "Server":
                            self.events_received_server_ack[measurement_id][1] = reason
                            self.events_received_server_ack[measurement_id][0].set()
                        elif role_conf_failed == "Client":
                            self.events_received_client_ack[measurement_id][1] = reason
                            self.events_received_client_ack[measurement_id][0].set()
                    case "stop":
                        print(f"Iperf_Coordinator: probe |{probe_sender}|->|Iperf stopped|->|NACK| : reason_payload -> {reason}")

            case _:
                print(f"Iperf_Coordinator: received unkown type message -> |{type}|")

        
    def send_probe_iperf_start(self, new_measurement : MeasurementModelMongo):        
        inserted_measurement_id = self.mongo_db.insert_measurement(new_measurement)
        if (inserted_measurement_id is None):
            return "Error", "Can't send start! Error while inserting measurement iperf in mongo", "MongoDB Down?"

        json_iperf_start = {
            "handler": "iperf",
            "command": "start",
            "payload": {
                "measurement_id": str(new_measurement._id)
            }
        }
        self.mqtt.publish_on_command_topic(probe_id = new_measurement.source_probe, complete_command = json.dumps(json_iperf_start))
        return "OK", new_measurement.to_dict(), None # By returning these arguments, it's possible to see them in the HTTP response

    def send_probe_iperf_conf(self, probe_id, json_config):
        json_command = {
            "handler": 'iperf',
            "command": "conf",
            "payload": json_config
        }        
        self.mqtt.publish_on_command_topic(probe_id = probe_id, complete_command=json.dumps(json_command))
    
    def send_probe_iperf_stop(self, probe_id, msm_id):
        json_iperf_stop = {
            "handler": "iperf",
            "command": "stop",
            "payload": {}
        }
        self.mqtt.publish_on_command_topic(probe_id = probe_id, complete_command = json.dumps(json_iperf_stop))


    def store_measurement_result(self, result : json):
        mongo_result = IperfResultModelMongo(
            msm_id = ObjectId(result["msm_id"]),
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
            measurement_id = result["msm_id"]
            if self.mongo_db.update_results_array_in_measurement(measurement_id):
                print(f"Iperf_Coordinator: updated document linking in measure: |{measurement_id}|")
            if self.mongo_db.set_measurement_as_completed(measurement_id):
                print(f"Iperf_Coordinator: measurement |{measurement_id}| completed ")
            self.send_probe_iperf_stop(self.queued_measurements[measurement_id].dest_probe, measurement_id)
        else:
            print("Iperf_Coordinator: result not last")


    def get_json_from_probe_yaml(self, probes_configurations_path) -> json:
        json_probe_config = {}
        with open(probes_configurations_path, "r") as file:
            iperf_client_config = yaml.safe_load(file)['iperf_client']
            json_probe_config = {
                "transport_protocol": iperf_client_config['transport_protocol'],
                "parallel_connections": int(iperf_client_config['parallel_connections']),
                "result_measurement_filename": iperf_client_config['result_measurement_filename'],
                "reverse": iperf_client_config['reverse'],
                "verbose": False, # YOU CANNOT SET VERBOSE WHEN USE JSON AS "STD-OUT"
                "total_repetition": int(iperf_client_config['total_repetition']),
                "save_result_on_flash": iperf_client_config['save_result_on_flash']
            }
        return json_probe_config


    def probes_preparer_to_measurements(self, new_measurement : MeasurementModelMongo):
        new_measurement.assign_id()
        measurement_id = str(new_measurement._id)
        self.events_received_server_ack[measurement_id] = [threading.Event(), None]
        self.queued_measurements[str(new_measurement._id)] = new_measurement

        json_config = {
                "role": "Server",
                "listen_port": 5201,
                "verbose": False,
                "measurement_id": measurement_id
            }
        
        self.send_probe_iperf_conf(probe_id = new_measurement.dest_probe, json_config = json_config) # Sending server configuration
        print("preparer iperf: sent conf server")
        self.events_received_server_ack[measurement_id][0].wait(timeout = 5) # Wait for the ACK server
        
        # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK FROM DEST_PROBE (IPERF-SERVER)

        server_event_message = self.events_received_server_ack[measurement_id][1]
        if server_event_message == "OK": # If the iperf-server configuration went good, then...
            print("preparer iperf: awake from server ACK ")
            base_path = Path(__file__).parent
            probes_configurations_path = Path(os.path.join(base_path, self.probes_configurations_dir, "configToBeClient.yaml"))
            if probes_configurations_path.exists():                                
                json_config = self.get_json_from_probe_yaml(probes_configurations_path)
                json_config['role'] = "Client"
                json_config['measurement_id'] = measurement_id
                json_config['destination_server_ip'] = new_measurement.dest_probe_ip
                json_config['destination_server_port'] = self.probes_server_port[new_measurement.dest_probe]

                self.send_probe_iperf_conf(probe_id = new_measurement.source_probe, json_config = json_config) # Sending client configuration
                self.events_received_client_ack[measurement_id] = [threading.Event(), None]
                self.events_received_client_ack[measurement_id][0].wait(timeout = 5)
                
                # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK FROM SOURCE_PROBE (IPERF-CLIENT)

                client_event_message = self.events_received_client_ack[measurement_id][1]
                if client_event_message == "OK":
                    return self.send_probe_iperf_start(new_measurement)
                
                self.send_probe_iperf_stop(new_measurement.dest_probe, measurement_id)
                if client_event_message is not None:
                    return "Error", f"Probe |{new_measurement.source_probe}| says: {client_event_message}", "State BUSY"
                else:
                    return "Error", f"No response from client probe: {new_measurement.source_probe}", "Reponse Timeout"
        elif server_event_message is not None:
            print(f"Preparer iperf: awaked from server conf NACK -> {server_event_message}")
            return "Error", f"Probe |{new_measurement.dest_probe}| says: {server_event_message}", "State BUSY"
        else:
            print(f"Preparer iperf: No response from server probe -> |{new_measurement.dest_probe}")
            return "Error", f"No response from Probe: {new_measurement.dest_probe}" , "Reponse Timeout"
        
    # NOT USED BUT USEFULL FOR TESTING
    def print_summary_result(self, measurement_result : json):
        start_timestamp = measurement_result["start_timestamp"]
        repetition_number = measurement_result["repetition_number"]
        msm_id = measurement_result["msm_id"]
        source_ip = measurement_result["source_ip"]
        transport_protocol = measurement_result["transport_protocol"]
        destination_ip = measurement_result["destination_ip"]
        bytes_received = measurement_result["bytes_received"]
        duration = measurement_result["duration"]
        avg_speed = measurement_result["avg_speed"]

        print("\n****************** SUMMARY ******************")
        print(f"Timestamp: {start_timestamp}")
        print(f"Repetition number: {repetition_number}")
        print(f"Measurement reference: {msm_id}")
        print(f"Transport protocol: {transport_protocol}")
        print(f"IP sorgente: {source_ip}")
        print(f"IP destinatario: {destination_ip}")
        print(f"Velocità trasferimento {avg_speed} bits/s")
        print(f"Quantità di byte ricevuti: {bytes_received}")
        print(f"Durata risultato: {duration} secondi\n")