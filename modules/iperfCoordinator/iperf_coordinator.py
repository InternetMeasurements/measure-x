"""
iperf_coordinator.py

This module defines the Iperf_Coordinator class, which manages the coordination of iperf-based network measurements between the coordinator and measurement probes in the Measure-X system. It handles configuration, starting, stopping, and result collection for iperf measurements, as well as communication with probes via MQTT and state management in MongoDB.
"""

import os
import json
import yaml
import time
import threading
import cbor2, base64, sys
from pathlib import Path
from modules.mqttModule.mqtt_client import Mqtt_Client
from bson import ObjectId
from modules.mongoModule.mongoDB import MongoDB, ErrorModel, SECONDS_OLD_MEASUREMENT
from modules.configLoader.config_loader import ConfigLoader, IPERF_CLIENT_KEY, IPERF_SERVER_KEY
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from modules.mongoModule.models.iperf_result_model_mongo import IperfResultModelMongo

class Iperf_Coordinator:
    """
    Coordinates iperf measurement tasks between the coordinator and probes.
    Handles registration of callbacks, preparation and stopping of measurements, and result processing.
    Communicates with probes using MQTT and manages measurement state in MongoDB.
    """

    def __init__(self, mqtt : Mqtt_Client, 
                 registration_handler_status_callback,
                 registration_handler_result_callback,
                 registration_measure_preparer_callback,
                 ask_probe_ip_mac_callback,
                 registration_measurement_stopper_callback,
                 mongo_db : MongoDB):
        """
        Initialize the Iperf_Coordinator and register all necessary callbacks for status, result, preparation, and stopping.
        Args:
            mqtt (Mqtt_Client): The MQTT client for communication with probes.
            registration_handler_status_callback (callable): Callback to register status handler.
            registration_handler_result_callback (callable): Callback to register result handler.
            registration_measure_preparer_callback (callable): Callback to register measurement preparer.
            ask_probe_ip_mac_callback (callable): Callback to get probe IP/MAC.
            registration_measurement_stopper_callback (callable): Callback to register measurement stopper.
            mongo_db (MongoDB): MongoDB interface for storing measurements and results.
        """
        self.mqtt = mqtt 
        self.probes_configurations_dir = 'probes_configurations'
        self.probes_server_port = {}
        self.ask_probe_ip_mac = ask_probe_ip_mac_callback
        self.mongo_db = mongo_db
        self.queued_measurements = {}
        self.events_received_server_ack = {}
        self.events_received_client_ack = {}
        self.events_stop_server_ack = {}

        # Requests to commands_multiplexer: handler STATUS registration
        registration_response = registration_handler_status_callback(
            interested_status = "iperf",
            handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"Iperf_Coordinator: registered handler for status -> iperf")
        else:
            print(f"Iperf_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Handler RESULT registration
        registration_response = registration_handler_result_callback(
            interested_result = "iperf",
            handler = self.handler_received_result)
        if registration_response == "OK" :
            print(f"Iperf_Coordinator: registered handler for result -> iperf")
        else:
            print(f"Iperf_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Probes-Preparer registration
        registration_response = registration_measure_preparer_callback(
            interested_measurement_type = "iperf",
            preparer_callback = self.probes_preparer_to_measurements)
        if registration_response == "OK" :
            print(f"Iperf_Coordinator: registered prepaper for measurements type -> iperf")
        else:
            print(f"Iperf_Coordinator: registration preparer failed. Reason -> {registration_response}")
        
        # Requests to commands_multiplexer: Measurement-Stopper registration
        registration_response = registration_measurement_stopper_callback(
            interested_measurement_type = "iperf",
            stopper_method_callback = self.iperf_measurement_stopper)
        if registration_response == "OK" :
            print(f"Iperf_Coordinator: registered measurement stopper for measurements type -> iperf")
        else:
            print(f"Iperf_Coordinator: registration measurement stopper failed. Reason -> {registration_response}")

        #self.print_average_compression_ratio() Compression computation


    def handler_received_result(self, probe_sender, result: json):
        """
        Handle result messages received from probes for iperf measurements.
        Stores the result if it is recent enough, otherwise ignores it.
        Args:
            probe_sender (str): The probe sending the result.
            result (json): The result message payload.
        """
        if ((time.time() - result["start_timestamp"]) < SECONDS_OLD_MEASUREMENT):
            self.store_measurement_result(probe_sender, result)
            #self.print_summary_result(measurement_result = result)
        else: #Volendo posso anche evitare questo settaggio, perchè ci penserà il thread periodico
            #if self.mongo_db.set_measurement_as_failed_by_id(result['msm_id']):
            print(f"Iperf_Coordinator: ignored result. Reason: expired measurement -> {result['msm_id']}")

        
    def handler_received_status(self, probe_sender, type, payload : json):
        """
        Handle status messages (ACK/NACK) received from probes for iperf commands.
        Updates internal events and state based on the received status.
        Args:
            probe_sender (str): The probe sending the status.
            type (str): The type of status message (ACK/NACK).
            payload (dict): The status message payload.
        """
        match type:
            case "ACK":
                command_executed_on_probe = payload["command"]
                match command_executed_on_probe:
                    case "conf":
                        measurement_id = payload["msm_id"]
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
                        measurement_id = payload["msm_id"]
                        if measurement_id is None:
                            print(f"Received ACK from |{probe_sender}| with None measurement -> IGNORE.")
                            return
                        if measurement_id in self.events_stop_server_ack:
                            self.events_stop_server_ack[measurement_id][1] = "OK"
                            self.events_stop_server_ack[measurement_id][0].set()
                            print(f"Iperf_Coordinator: probe |{probe_sender}| , stop -> |ACK| , msm_id -> {measurement_id}")
                        self.probes_server_port.pop(probe_sender, None)
                    case _:
                        print(f"ACK received for unkonwn iperf command -> {command_executed_on_probe}")
            case "NACK":
                command_failed_on_probe = payload["command"]
                reason = payload['reason']
                measurement_id = payload["msm_id"] if ('msm_id' in payload) else None
                role_conf_failed = payload["role"] if ('role' in payload) else None
                print(f"Iperf_Coordinator: probe |{probe_sender}|->|{command_failed_on_probe}|->|NACK|, reason_payload --> {reason}, measure --> {measurement_id}")
                match command_failed_on_probe:
                    case "start":
                        if self.mongo_db.set_measurement_as_failed_by_id(measurement_id = measurement_id):
                            print(f"Iperf_Coordinator: measurement |{measurement_id}| setted as failed")
                        if role_conf_failed == "Client":
                            if measurement_id is not None: # I must stop the iperf server on the probe
                                if measurement_id not in self.events_stop_server_ack:
                                    self.send_probe_iperf_stop(self.queued_measurements[measurement_id].dest_probe, measurement_id)
                    case "conf":
                        if role_conf_failed == "Server":
                            self.events_received_server_ack[measurement_id][1] = reason
                            self.events_received_server_ack[measurement_id][0].set()
                        elif role_conf_failed == "Client":
                            self.events_received_client_ack[measurement_id][1] = reason
                            self.events_received_client_ack[measurement_id][0].set()
                    case "stop":
                        if measurement_id is None:
                            print(f"Iperf_Coordinator: probe |{probe_sender}|->|Iperf stopped|->|NACK| : None measure")
                        else:
                            print(f"Iperf_Coordinator: probe |{probe_sender}|->|Iperf stopped|->|NACK| : reason_payload -> {reason}")
                            #if (role_conf_failed is not None) and (role_conf_failed == "Server"):
                            if measurement_id in self.events_stop_server_ack:
                                self.events_stop_server_ack[measurement_id][1] = reason
                                self.events_stop_server_ack[measurement_id][0].set()
            case _:
                print(f"Iperf_Coordinator: received unkown type message -> |{type}|")

        
    def send_probe_iperf_start(self, new_measurement : MeasurementModelMongo):
        """
        Send a start command to the probe to begin an iperf measurement.
        Inserts the measurement into MongoDB before sending the command.
        Args:
            new_measurement (MeasurementModelMongo): The measurement to start.
        Returns:
            tuple: (status, message, error_cause)
        """
        new_measurement.parameters.pop("output_iperf_dir", None)
        new_measurement.parameters.pop("save_result_on_flash", None)
        new_measurement.parameters.pop("verbose", None)
        new_measurement.parameters.pop("result_measurement_filename", None)
        new_measurement.parameters.pop("role", None)
        
        

        inserted_measurement_id = self.mongo_db.insert_measurement(new_measurement)
        if (inserted_measurement_id is None):
            return "Error", "Can't send start! Error while inserting measurement iperf in mongo", "MongoDB Down?"

        json_iperf_start = {
            "handler": "iperf",
            "command": "start",
            "payload": {
                "msm_id": str(new_measurement._id)
            }
        }
        self.mqtt.publish_on_command_topic(probe_id = new_measurement.source_probe, complete_command = json.dumps(json_iperf_start))
        return "OK", new_measurement.to_dict(), None # By returning these arguments, it's possible to see them in the HTTP response

    def send_probe_iperf_conf(self, probe_id, json_config):
        """
        Send a configuration command to a probe for iperf setup.
        Args:
            probe_id (str): The probe to configure.
            json_config (dict): The configuration payload.
        """
        json_command = {
            "handler": 'iperf',
            "command": "conf",
            "payload": json_config
        }        
        self.mqtt.publish_on_command_topic(probe_id = probe_id, complete_command=json.dumps(json_command))
    
    def send_probe_iperf_stop(self, probe_id, msm_id):
        """
        Send a stop command to a probe to terminate an iperf measurement.
        Args:
            probe_id (str): The probe to stop.
            msm_id (str): The measurement ID to stop.
        """
        json_iperf_stop = {
            "handler": "iperf",
            "command": "stop",
            "payload": {
                "msm_id": msm_id
            }
        }
        self.mqtt.publish_on_command_topic(probe_id = probe_id, complete_command = json.dumps(json_iperf_stop))

    
    def get_size(self, obj):
        """
        Recursively compute the size in bytes of a Python object, including nested structures.
        Args:
            obj: The object to measure.
        Returns:
            int: The total size in bytes.
        """
        if isinstance(obj, dict):
            return sys.getsizeof(obj) + sum(self.get_size(k) + self.get_size(v) for k, v in obj.items())
        elif isinstance(obj, (list, tuple, set)):
            return sys.getsizeof(obj) + sum(self.get_size(i) for i in obj)
        else:
            return sys.getsizeof(obj)

    def store_measurement_result(self, probe_sender, result : json):
        """
        Store the result of an iperf measurement in MongoDB and update measurement state.
        Decodes and processes the result, and triggers completion logic if this is the last result.
        Args:
            probe_sender (str): The probe sending the result.
            result (json): The result message payload.
        """
        msm_id = result["msm_id"] if "msm_id" in result else None
        if msm_id is None:
            print(f"Iperf_Coordinator: received result from probe |{probe_sender}| -> No measure_id provided. IGNORE.")
            return
        full_result_c_b64 = result["full_result_c_b64"] if ("full_result_c_b64" in result) else None # Full Result Compressed and 64Based
        if full_result_c_b64 is not None:
            c_full_result = base64.b64decode(full_result_c_b64)
            full_result = cbor2.loads(c_full_result)
        else:
            print(f"Iperf_Coordinator: WARNING -> received result without full_result , measure_id -> {result['msm_id']}")
            full_result = None

        mongo_result = IperfResultModelMongo(
            msm_id = ObjectId(msm_id),
            repetition_number = result["repetition_number"],
            start_timestamp = result["start_timestamp"],
            transport_protocol = result["transport_protocol"],
            source_ip = result["source_ip"],
            source_port = result["source_port"],
            destination_ip = result["destination_ip"],
            destination_port = result["destination_port"],
            bytes_received = result["bytes_received"],
            duration = result["duration"],
            avg_speed = result["avg_speed"] / 10**6, # Speed in Mbps
            full_result = full_result
        )

        #size_1 = self.get_size(full_result)
        #size_2 = self.get_size(full_result_c_b64)
        #print(f"************************************************** Size full_result without compression: |{size_1}| byte , Size full_result with compression: |{size_2}| byte")
        #self.save_result_on_csv(size_1, size_2)
        #print(f"full_result -> |{full_result}|")
        #print("----------------------------------------------------------------")
        #print(f"full_result_c_b64 -> |{full_result_c_b64}|")

        result_id = str(self.mongo_db.insert_result(result=mongo_result))
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
#        else:
#            print("Iperf_Coordinator: result not last")


    def get_default_iperf_parameters(self, role) -> json:
        """
        Load the default iperf parameters for a given role (Client or Server) from configuration files.
        Args:
            role (str): 'Client' or 'Server'.
        Returns:
            dict: The default configuration for the specified role.
        """
        base_path = os.path.join(Path(__file__).parent, "probes_configurations")

        config_file_name =  "configToBeClient.yaml" if (role == "Client") else "configToBeServer.yaml"
        IPERF_KEY = IPERF_CLIENT_KEY if (role == "Client") else IPERF_SERVER_KEY

        cl = ConfigLoader(base_path= base_path, file_name = config_file_name, KEY = IPERF_KEY)
        json_default_config = cl.config if (cl.config is not None) else {}
        json_default_config['role'] = role
        return json_default_config

    def override_default_parameters(self, json_config, measurement_parameters, role):
        """
        Override the default iperf parameters with those specified in the measurement parameters.
        Args:
            json_config (dict): The default configuration.
            measurement_parameters (dict): The parameters to override.
            role (str): 'Client' or 'Server'.
        Returns:
            dict: The overridden configuration.
        """
        json_overrided_config = json_config
        if (measurement_parameters is not None) and (isinstance(measurement_parameters, dict)):
            if role == "Client":
                if ('transport_protocol' in measurement_parameters):
                    protocol = measurement_parameters['transport_protocol'].lower()
                    if (protocol  == "udp") or (protocol == "tcp"):
                        json_overrided_config['transport_protocol'] = measurement_parameters['transport_protocol']
                if ('parallel_connections' in measurement_parameters):
                    json_overrided_config['parallel_connections'] = measurement_parameters['parallel_connections']
                if ('result_measurement_filename' in measurement_parameters):
                    json_overrided_config['result_measurement_filename'] = measurement_parameters['result_measurement_filename']
                if ('reverse' in measurement_parameters):
                    json_overrided_config['reverse'] = measurement_parameters['reverse']
                if ('repetitions' in measurement_parameters):
                    json_overrided_config['repetitions'] = measurement_parameters['repetitions']
                if ('save_result_on_flash' in measurement_parameters):
                    json_overrided_config['save_result_on_flash'] = measurement_parameters['save_result_on_flash']
            elif role == "Server":
                if 'listen_port' in measurement_parameters:
                    json_overrided_config['listen_port'] = measurement_parameters['listen_port']
        return json_overrided_config

            


    def probes_preparer_to_measurements(self, new_measurement : MeasurementModelMongo):
        """
        Prepare the probes for a new iperf measurement and start the measurement process.
        Waits for ACK/NACK from both server and client probes and stores the measurement in MongoDB if successful.
        Args:
            new_measurement (MeasurementModelMongo): The measurement to prepare and start.
        Returns:
            tuple: (status, message, error_cause)
        """
        new_measurement.assign_id()
        measurement_id = str(new_measurement._id)

        if new_measurement.source_probe is None:
            return "Error", f"No source probe id provided", "Missing source_probe parameter"

        if new_measurement.dest_probe is None:
            return "Error", f"No destination probe id provided", "Missing dest_probe parameter"

        source_probe_ip, _ = self.ask_probe_ip_mac(new_measurement.source_probe)
        if source_probe_ip is None:
            return "Error", f"No response from client probe: {new_measurement.source_probe}", "Reponse Timeout"

        dest_probe_ip, _ = self.ask_probe_ip_mac(new_measurement.dest_probe)
        if dest_probe_ip is None:
            return "Error", f"No response from client probe: {new_measurement.dest_probe}", "Reponse Timeout"

        new_measurement.source_probe_ip = source_probe_ip
        new_measurement.dest_probe_ip = dest_probe_ip

        self.events_received_server_ack[measurement_id] = [threading.Event(), None]
        self.queued_measurements[str(new_measurement._id)] = new_measurement

        json_server_config = self.get_default_iperf_parameters(role="Server")
        json_server_config = self.override_default_parameters(json_server_config, new_measurement.parameters, role="Server")
        json_server_config["msm_id"] = measurement_id

        
        self.send_probe_iperf_conf(probe_id = new_measurement.dest_probe, json_config = json_server_config) # Sending server configuration
        print("preparer iperf: sent conf server")
        self.events_received_server_ack[measurement_id][0].wait(timeout = 5) # Wait for the ACK server
        
        # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK FROM DEST_PROBE (IPERF-SERVER)

        server_event_message = self.events_received_server_ack[measurement_id][1]
        if server_event_message == "OK": # If the iperf-server configuration went good, then...
            print("preparer iperf: awake from server ACK ")
            
            json_client_config = self.get_default_iperf_parameters(role="Client")
            json_client_config = self.override_default_parameters(json_client_config, new_measurement.parameters, role = "Client")

            # -----------------------------------------------------------------------------------------
            parameters_to_store_in_measurement = json_client_config.copy()
            parameters_to_store_in_measurement['listen_port'] = json_server_config['listen_port']
            new_measurement.parameters = parameters_to_store_in_measurement
            # This line above ensures that all parameters are included in the measurement object,
            # even those that are not explicitly specified in measurement-subscription phase.

            json_client_config['msm_id'] = measurement_id
            json_client_config['destination_server_ip'] = dest_probe_ip
            json_client_config['destination_server_port'] = self.probes_server_port[new_measurement.dest_probe]
            # The upper line code is a mechanism to automatic set the client port equal to the chosen server port.

            self.send_probe_iperf_conf(probe_id = new_measurement.source_probe, json_config = json_client_config) # Sending client configuration
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
            return "Error", f"No response from Probe: {new_measurement.dest_probe}" , "Response Timeout"

    def iperf_measurement_stopper(self, msm_id_to_stop : str):
        """
        Stop an ongoing iperf measurement by sending a stop command to the probe.
        Waits for an ACK/NACK from the probe and returns the result.
        Args:
            msm_id_to_stop (str): The measurement ID to stop.
        Returns:
            tuple: (status, message, error_cause)
        """
        if msm_id_to_stop not in self.queued_measurements:
            measure_from_db : MeasurementModelMongo = self.mongo_db.find_measurement_by_id(measurement_id=msm_id_to_stop)
            if isinstance(measure_from_db, ErrorModel):
                return "Error", measure_from_db.error_description, measure_from_db.error_cause
            self.queued_measurements[msm_id_to_stop] = measure_from_db
        
        measurement_to_stop : MeasurementModelMongo = self.queued_measurements[msm_id_to_stop]
        self.events_stop_server_ack[msm_id_to_stop] = [threading.Event(), None]
        self.send_probe_iperf_stop(probe_id=measurement_to_stop.dest_probe, msm_id=msm_id_to_stop)
        self.events_stop_server_ack[msm_id_to_stop][0].wait(5)
        # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK OF STOP COMMAND FROM DEST PROBE (IPERF-SERVER)
        stop_event_message = self.events_stop_server_ack[msm_id_to_stop][1]
        if stop_event_message == "OK":
            return "OK", f"Measurement {msm_id_to_stop} stopped.", None
        if stop_event_message is not None:
            return "Error", f"Probe |{measurement_to_stop.dest_probe}| says: |{stop_event_message}|", ""
        return "Error", f"Can't stop the measurement -> |{msm_id_to_stop}|", f"No response from probe server |{measurement_to_stop.dest_probe}|"
        
        
        
    
    # NOT USED BUT USEFULL FOR TESTING
    def print_summary_result(self, measurement_result : json):
        """
        Print a summary of the iperf measurement result for debugging or analysis.
        Args:
            measurement_result (json): The result message payload.
        """
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


# **********************************  PLUS: Methods for Compression Percentage Computation **********************************
"""
    def save_result_on_csv(self, size_1, size_2):
        import csv
        with open("iperf_uncomp_vs_comp.csv", mode="a", newline="") as csv_file:
            fieldnames = ["Uncompressed", "Compressed"]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

            if os.stat("iperf_uncomp_vs_comp.csv").st_size == 0:
                writer.writeheader()

            writer.writerow({"Uncompressed": size_1, "Compressed": size_2})

    def print_average_compression_ratio(self, file_path="iperf_uncomp_vs_comp.csv"):
        import pandas as pd

        try:
            df = pd.read_csv(file_path)

            df['Compression_Percentage'] = ( 1 - (df['Compressed'] / df['Uncompressed']) ) * 100

            compressed_mean = df['Compressed'].mean().__ceil__()
            uncompressed_mean = df['Uncompressed'].mean().__ceil__()

            print(f"compressed_mean: Value -> {compressed_mean} byte")
            print(f"uncompressed_mean: Value -> {uncompressed_mean}")

            compression_percentage = df['Compression_Percentage'].mean()
            print(f"IPERF: Average compression percentage: {compression_percentage}%")

        except FileNotFoundError:
            print("File not found.")
            return None
        except pd.errors.EmptyDataError:
            print("No data in file.")
            return None
        except KeyError:
            print("Missing 'Uncompressed' or 'Compressed' columns in the file.")
            return None"
"""