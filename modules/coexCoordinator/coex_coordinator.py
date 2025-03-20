import os
from pathlib import Path
import json
import time
import threading
from datetime import datetime as dt
from modules.mqttModule.mqtt_client import Mqtt_Client
from modules.configLoader.config_loader import ConfigLoader, COEX_KEY
from bson import ObjectId
from modules.mongoModule.mongoDB import MongoDB, SECONDS_OLD_MEASUREMENT, ErrorModel
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from modules.mongoModule.models.coex_result_model_mongo import CoexResultModelMongo

class Coex_Coordinator:

    def __init__(self, mqtt_client : Mqtt_Client, 
                 registration_handler_error_callback, registration_handler_status_callback,
                 registration_handler_result_callback, registration_measure_preparer_callback,
                 ask_probe_ip_mac_callback, registration_measurement_stopper_callback,
                 mongo_db : MongoDB):
        self.mqtt_client = mqtt_client
        self.mongo_db = mongo_db
        self.ask_probe_ip_mac = ask_probe_ip_mac_callback
        self.events_received_ack_from_probe_sender = {}
        self.events_received_stop_ack = {}
        self.queued_measurements = {}

        registration_response = registration_handler_error_callback( interested_error = "coex",
                                                             handler = self.handler_received_error)
        if registration_response == "OK" :
            print(f"Coex_Coordinator: registered handler for error -> coex")
        else:
            print(f"Coex_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: handler STATUS registration
        registration_response = registration_handler_status_callback( interested_status = "coex",
                                                             handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"Coex_Coordinator: registered handler for status -> coex")
        else:
            print(f"Coex_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: handler RESULT registration
        registration_response = registration_handler_result_callback(interested_result = "coex",
                                                            handler = self.handler_received_result)
        if registration_response == "OK" :
            print(f"Coex_Coordinator: registered handler for result -> coex")
        else:
            print(f"Coex_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Probes-Preparer registration
        registration_response = registration_measure_preparer_callback(
            interested_measurement_type = "coex",
            preparer_callback = self.probes_preparer_to_measurements)
        if registration_response == "OK" :
            print(f"Coex_Coordinator: registered prepaper for measurements type -> coex")
        else:
            print(f"Coex_Coordinator: registration preparer failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Measurement-Stopper registration
        registration_response = registration_measurement_stopper_callback(
            interested_measurement_type = "coex",
            stopper_method_callback = self.coex_measurement_stopper)
        if registration_response == "OK" :
            print(f"Coex_Coordinator: registered measurement stopper for measurements type -> coex")
        else:
            print(f"Coex_Coordinator: registration measurement stopper failed. Reason -> {registration_response}")


    def handler_received_status(self, probe_sender, type, payload : json):
        msm_id = payload["msm_id"] if ("msm_id" in payload) else None
        command = payload["command"] if ("command" in payload) else None
        match type:
            case "ACK":                
                if (command == "conf") or (command == "start"):
                    if msm_id in self.events_received_ack_from_probe_sender:
                        self.events_received_ack_from_probe_sender[msm_id][1] = "OK"
                        self.events_received_ack_from_probe_sender[msm_id][0].set()
                elif command == "stop":
                    if msm_id is None:
                        print(f"Coex_Coordinator: received |stop| ACK from probe |{probe_sender}| wihout measure_id")
                        return
                    if msm_id not in self.queued_measurements: # If the coordinator has been rebooted in the while...
                        measurement_from_mongo = self.mongo_db.find_measurement_by_id(measurement_id=msm_id)
                        if not isinstance(measurement_from_mongo, MeasurementModelMongo):
                            print(f"Coex_Coordinator: received |stop| ACK of measurement not stored in DB -> |{msm_id}|")
                            return
                        self.queued_measurements[msm_id] = measurement_from_mongo
                    # If the measurement is not completed AND the probe sender is the probe client, then i will stop also the server probe
                    if (self.queued_measurements[msm_id].state == "started") and (self.queued_measurements[msm_id].source_probe == probe_sender):
                        print(f"Coex_Coordinator: received |stop| ACK from |{probe_sender}|. Stopping the server probe |{self.queued_measurements[msm_id].dest_probe}|")
                        self.send_probe_coex_stop(probe_id=self.queued_measurements[msm_id].dest_probe, msm_id_to_stop=msm_id)
                    if msm_id in self.events_received_stop_ack:
                        self.events_received_stop_ack[msm_id][1] = "OK"
                        self.events_received_stop_ack[msm_id][0].set()
                else:
                    print(f"Coex_Coordinator: received ACK from probe |{probe_sender}| , UNKNOWN COMMAND -> |{command}|")
                    return
                print(f"Coex_Coordinator: received ACK from probe |{probe_sender}| , command -> |{command}|")

            case "NACK":
                reason = payload['reason']
                print(f"Coex_Coordinator: WARNING --> NACK from |{probe_sender}| , command: |{command}| , reason: |{reason}|")
                if command == "conf":
                    if msm_id in self.events_received_ack_from_probe_sender:
                        self.events_received_ack_from_probe_sender[msm_id][1] = reason
                        self.events_received_ack_from_probe_sender[msm_id][0].set()
                elif command == "start":
                    if msm_id in self.events_received_ack_from_probe_sender:
                        self.events_received_ack_from_probe_sender[msm_id][1] = reason
                        self.events_received_ack_from_probe_sender[msm_id][0].set()
                elif command == "stop":
                    if msm_id in self.events_received_stop_ack:
                        self.events_received_stop_ack[msm_id][1] = reason
                        self.events_received_stop_ack[msm_id][0].set()
            
            case _:
                print(f"Coex_Coordinator: received unkown type message -> |{type}|")

    def handler_received_result(self, probe_sender, result: json):
        measure_id = result['msm_id'] if ('msm_id' in result) else None
        if measure_id is None:
            print("Coex_Coordinator: received result wihout measure_id -> IGNORED")
            return
        
        if ((time.time() - result["timestamp"]) < SECONDS_OLD_MEASUREMENT):
            if self.store_measurement_result(result = result):
                print(f"Coex_Coordinator: complete the measurement store and update -> {measure_id}")
        else:
            print(f"Coex_Coordinator: ignored result. Reason: expired measurement -> {measure_id}")

    def handler_received_error(self, probe_sender, error_command, error_payload : json):
        print(f"Coex_Coordinator: error from {probe_sender} , command |{error_command}| payload: {error_payload}")
        if error_command == "socket":
            msm_id = error_payload['msm_id'] if ('msm_id' in error_payload) else None
            if msm_id == None:
                print(f"Coex_Coordinator: None error relative measure")
                return
            reason = error_payload['reason'] if ('reason' in error_payload) else None
            print(f"\t error in measure {msm_id}, reason: {reason}")
            if msm_id not in self.queued_measurements:
                referred_measure = self.mongo_db.find_measurement_by_id(measurement_id=msm_id)
                if not isinstance(referred_measure, MeasurementModelMongo):
                    print(f"Coex_Coordinator: relative measure not found -> |{msm_id}|")
                    return
            else:
                referred_measure = self.queued_measurements[msm_id]

            if (referred_measure.state != "failed") and (referred_measure.state != "completed"):
                error_probe_is_server = (probe_sender == referred_measure.dest_probe) # Verifying if the probe_sender is the measurement server.
                if error_probe_is_server:
                    self.send_probe_coex_stop(probe_id=referred_measure.source_probe, msm_id_to_stop=msm_id)
                    self.events_received_ack_from_probe_sender[msm_id][1] = reason
                    print(f"Coex_Coordinator: stopped probe |{referred_measure.source_probe}| involved in error relative measure -> |{msm_id}|")
        else:
            print(f"Coex_Coordinator: error unknown command -> {error_command}")

    def send_probe_coex_conf(self, probe_sender, msm_id, role, parameters, counterpart_probe_mac, server_probe_ip = None):
        json_conf_payload = {
            "msm_id": msm_id,
            "role": role,
            "packets_size": parameters["packets_size"],
            "packets_number": parameters["packets_number"],
            "packets_rate" : parameters["packets_rate"],
            "socket_port" : parameters["socket_port"],
            "server_probe_ip": server_probe_ip,
            "counterpart_probe_mac": counterpart_probe_mac
        }
        
        json_coex_conf = {
            "handler": "coex",
            "command": "conf",
            "payload": json_conf_payload
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_coex_conf))


    def send_probe_coex_start(self, probe_id, msm_id):
        json_coex_start = {
            "handler": "coex",
            "command": "start",
            "payload": {
                "msm_id": msm_id
            }
        }
        self.mqtt_client.publish_on_command_topic(probe_id=probe_id, complete_command=json.dumps(json_coex_start))


    def send_probe_coex_stop(self, probe_id, msm_id_to_stop):
        json_coex_stop = {
            "handler": "coex",
            "command": "stop",
            "payload": {
                "msm_id": msm_id_to_stop
            }
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_id, complete_command=json.dumps(json_coex_stop))

    
    def store_measurement_result(self, result : json) -> bool:
        coex_result = CoexResultModelMongo()
        result_id = str(self.mongo_db.insert_result(result = coex_result))
        if result_id is not None:
            msm_id = result["msm_id"]
            print(f"Coex_Coordinator: result |{result_id}| stored in db")
            if self.mongo_db.update_results_array_in_measurement(msm_id):
                print(f"Coex_Coordinator: updated document linking in measure: |{msm_id}|")
                if self.mongo_db.set_measurement_as_completed(msm_id):
                    self.print_summary_result(measurement_result = result)
                    return True
        print(f"Coex_Coordinator: error while storing result |{result_id}|")
        return False


    def probes_preparer_to_measurements(self, new_measurement : MeasurementModelMongo):
        new_measurement.assign_id()
        measurement_id = str(new_measurement._id)

        coex_parameters = self.get_default_coex_parameters()
        coex_parameters = self.override_default_parameters(coex_parameters, new_measurement.parameters)

        source_probe_ip, source_probe_mac = self.ask_probe_ip_mac(new_measurement.source_probe)
        if (source_probe_ip is None):
            return "Error", f"No response from client probe: {new_measurement.source_probe}", "Reponse Timeout"
        dest_probe_ip, dest_probe_mac = self.ask_probe_ip_mac(new_measurement.dest_probe)
        if dest_probe_ip is None:
            return "Error", f"No response from client probe: {new_measurement.dest_probe}", "Reponse Timeout"
        
        new_measurement.source_probe_ip = source_probe_ip
        new_measurement.dest_probe_ip = dest_probe_ip
        new_measurement.parameters = coex_parameters.copy()
        self.queued_measurements[measurement_id] = new_measurement
        
        self.events_received_ack_from_probe_sender[measurement_id] = [threading.Event(), None]
        self.send_probe_coex_conf(probe_sender = new_measurement.dest_probe, msm_id = measurement_id, role="Server", parameters=new_measurement.parameters,
                                  counterpart_probe_mac = source_probe_mac)

        self.events_received_ack_from_probe_sender[measurement_id][0].wait(timeout = 5)
        # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK FROM DEST_PROBE (COEX INITIATOR)

        probe_server_conf_message = self.events_received_ack_from_probe_sender[measurement_id][1]
        if probe_server_conf_message == "OK":
            self.events_received_ack_from_probe_sender[measurement_id] = [threading.Event(), None]
            self.send_probe_coex_conf(probe_sender = new_measurement.source_probe, msm_id = measurement_id, role="Client",
                                      parameters=new_measurement.parameters, server_probe_ip=new_measurement.dest_probe_ip,
                                      counterpart_probe_mac = dest_probe_mac)
            self.events_received_ack_from_probe_sender[measurement_id][0].wait(timeout = 5)
            # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK FROM SOURCE_PROBE (COEX INITIATOR)
            probe_client_conf_message = self.events_received_ack_from_probe_sender[measurement_id][1]
            if probe_client_conf_message == "OK":
                self.events_received_ack_from_probe_sender[measurement_id] = [threading.Event(), None]
                self.send_probe_coex_start(probe_id=new_measurement.source_probe, msm_id=measurement_id)
                self.events_received_ack_from_probe_sender[measurement_id][0].wait(timeout = 5)
                # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK START FROM SOURCE_PROBE (COEX INITIATOR)
                probe_client_start_message = self.events_received_ack_from_probe_sender[measurement_id][1]
                if probe_client_start_message == "OK":
                    inserted_measurement_id = self.mongo_db.insert_measurement(measure = new_measurement)
                    if inserted_measurement_id is None:
                        print(f"Coex_Coordinator: can't start coex. Error while storing coex measurement on Mongo")
                        return "Error", "Can't send start! Error while inserting measurement coex in mongo", "MongoDB Down?"
                    self.queued_measurements[measurement_id] = new_measurement
                    return "OK", new_measurement.to_dict(), None
                
                # Sending stop to the server probe, otherwise it will remain BUSY
                self.send_probe_coex_stop(probe_id=new_measurement.dest_probe, msm_id_to_stop=measurement_id) 
                if probe_client_start_message is not None:
                    print(f"Preparer coex: awaked from client start NACK -> {probe_client_start_message}")
                    return "Error", f"Probe |{new_measurement.source_probe}| says: {probe_server_conf_message}", ""      
                else:
                    print(f"Preparer coex: No response from probe -> |{new_measurement.source_probe}")
                    return "Error", f"No response from Probe: {new_measurement.source_probe}" , "Response Timeout"
            
            # Sending stop to the server probe, otherwise it will remain BUSY
            self.send_probe_coex_stop(probe_id=new_measurement.dest_probe, msm_id_to_stop=measurement_id)
            if probe_client_conf_message is not None:
                print(f"Preparer coex: awaked from client conf NACK -> {probe_client_conf_message}")
                
                return "Error", f"Probe |{new_measurement.source_probe}| says: {probe_server_conf_message}", ""      
            else:
                print(f"Preparer coex: No response from probe -> |{new_measurement.source_probe}")
                # Sending stop to the server probe, otherwise it will remain BUSY
                self.send_probe_coex_stop(probe_id=new_measurement.dest_probe, msm_id_to_stop=measurement_id) 
                return "Error", f"No response from Probe: {new_measurement.source_probe}" , "Response Timeout"
        elif probe_server_conf_message is not None:
            print(f"Preparer coex: awaked from server conf NACK -> {probe_server_conf_message}")
            return "Error", f"Probe |{new_measurement.dest_probe}| says: {probe_server_conf_message}", ""            
        else:
            print(f"Preparer coex: No response from probe -> |{new_measurement.dest_probe}")
            return "Error", f"No response from Probe: {new_measurement.dest_probe}" , "Response Timeout"


    def coex_measurement_stopper(self, msm_id_to_stop : str):
        if msm_id_to_stop not in self.queued_measurements:
            measure_from_db : MeasurementModelMongo = self.mongo_db.find_measurement_by_id(measurement_id=msm_id_to_stop)
            if isinstance(measure_from_db, ErrorModel):
                return "Error", measure_from_db.error_description, measure_from_db.error_cause
            self.queued_measurements[msm_id_to_stop] = measure_from_db

        measurement_to_stop : MeasurementModelMongo = self.queued_measurements[msm_id_to_stop]
        self.events_received_stop_ack[msm_id_to_stop] = [threading.Event(), None]
        self.send_probe_coex_stop(probe_id = measurement_to_stop.dest_probe, msm_id_to_stop = msm_id_to_stop)
        self.events_received_stop_ack[msm_id_to_stop][0].wait(5)
        # ------------------------------- WAIT FOR RECEIVE AN ACK/NACK -------------------------------
        stop_event_message = self.events_received_stop_ack[msm_id_to_stop][1]
        if stop_event_message == "OK":
            self.events_received_stop_ack[msm_id_to_stop] = [threading.Event(), None]
            self.send_probe_coex_stop(probe_id = measurement_to_stop.source_probe, msm_id_to_stop = msm_id_to_stop)
            self.events_received_stop_ack[msm_id_to_stop][0].wait(5)
            stop_event_message = self.events_received_stop_ack[msm_id_to_stop][1]
            if stop_event_message == "OK":
                if self.mongo_db.set_measurement_as_completed(msm_id_to_stop):
                    print(f"Coex_Coordinator: measurement |{msm_id_to_stop}| setted as completed")
                else:
                    print(f"Coex_Coordinator: error while setting |completed| the measure --> |{msm_id_to_stop}|")
                return "OK", f"Measurement {msm_id_to_stop} stopped", None
            if stop_event_message is not None:
                return "Error", f"Probe |{measurement_to_stop.source_probe}| says: |{stop_event_message}|", ""
            return "Error", f"Can't stop the measurement -> |{msm_id_to_stop}|", f"No response from probe |{measurement_to_stop.source_probe}|"
        
        self.send_probe_coex_stop(probe_id = measurement_to_stop.source_probe, msm_id_to_stop = msm_id_to_stop)
        if self.mongo_db.set_measurement_as_completed(msm_id_to_stop):
            print(f"Coex_Coordinator: measurement |{msm_id_to_stop}| setted as completed")
        
        if stop_event_message is not None:
            return "Error", f"Probe |{measurement_to_stop.dest_probe}| says: |{stop_event_message}|", ""
        return "Error", f"Can't stop the measurement -> |{msm_id_to_stop}|", f"No response from probe |{measurement_to_stop.dest_probe}|"
    

    def get_default_coex_parameters(self) -> json:
        base_path = os.path.join(Path(__file__).parent)       
        cl = ConfigLoader(base_path= base_path, file_name = "default_parameters.yaml", KEY = COEX_KEY)
        json_default_config = cl.config if (cl.config is not None) else {}
        return json_default_config

    def override_default_parameters(self, json_config, measurement_parameters):
        json_overrided_config = json_config
        if (measurement_parameters is not None) and (isinstance(measurement_parameters, dict)):
            if ('packets_number' in measurement_parameters):
                json_overrided_config['packets_number'] = measurement_parameters['packets_number']
            if ('packets_size' in measurement_parameters):
                json_overrided_config['packets_size'] = measurement_parameters['packets_size']
            if ('packets_rate' in measurement_parameters):
                json_overrided_config['packets_rate'] = measurement_parameters['packets_rate']
            if ('socket_port' in measurement_parameters):
                json_overrided_config['socket_port'] = measurement_parameters['socket_port']
                
        return json_overrided_config