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
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo, CoexistingApplicationModelMongo

class Coex_Coordinator:

    def __init__(self, mqtt_client : Mqtt_Client, 
                 registration_handler_error_callback, registration_handler_status_callback,
                 registration_measure_preparer_callback,
                 ask_probe_ip_mac_callback, registration_measurement_stopper_callback,
                 mongo_db : MongoDB):
        self.mqtt_client = mqtt_client
        self.mongo_db = mongo_db
        self.ask_probe_ip_mac = ask_probe_ip_mac_callback
        self.events_received_ack_from_probe_sender = {}
        self.events_stop_probe_ack = {}
        self.queued_measurements = {}
        self.coex_stop_ack_number = {} # IF it is received an ACK or NACK, also the other probe is stopped

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
                    if msm_id not in self.coex_stop_ack_number:
                        self.coex_stop_ack_number[msm_id] = 0
                        
                    # If the measurement is not completed AND the probe sender is the probe client, then i will stop also the server probe
                    if (self.queued_measurements[msm_id].state == "started") and (self.queued_measurements[msm_id].coexisting_application["source_probe"] == probe_sender):
                        print(f"Coex_Coordinator: received |stop| ACK from |{probe_sender}|. Stopping the server probe |{self.queued_measurements[msm_id].coexisting_application['dest_probe']}|")
                        self.send_probe_coex_stop(probe_id=self.queued_measurements[msm_id].coexisting_application["dest_probe"], msm_id_to_stop=msm_id, silent = True)
                    self.coex_stop_ack_number[msm_id] += 1
                    if msm_id in self.events_stop_probe_ack:
                        self.events_stop_probe_ack[msm_id][1] = "OK"
                        self.events_stop_probe_ack[msm_id][0].set()
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
                    else:
                        if msm_id in self.queued_measurements: # If the coordinator has been rebooted in the while...
                            source_probe = self.queued_measurements[msm_id].source_probe
                            if probe_sender == source_probe:
                                self.send_probe_coex_stop(probe_id=self.queued_measurements[msm_id].dest_probe, msm_id_to_stop=msm_id)
                elif command == "stop":
                    if msm_id in self.events_stop_probe_ack:
                        self.events_stop_probe_ack[msm_id][1] = reason
                        self.events_stop_probe_ack[msm_id][0].set()
            case _:
                print(f"Coex_Coordinator: received unkown type message -> |{type}|")


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

    def send_probe_coex_conf(self, probe_sender, msm_id, role, parameters : CoexistingApplicationModelMongo, 
                             counterpart_probe_mac, counterpart_probe_ip = None):
        
        json_conf_payload = {
            "msm_id": msm_id,
            "role": role,
            "packets_size": parameters.packets_size, #parameters["packets_size"],
            "packets_number": parameters.packets_number, #["packets_number"],
            "packets_rate" : parameters.packets_rate, #["packets_rate"],
            "socket_port" : parameters.socket_port, #["socket_port"],
            "trace_name" : parameters.trace_name,
            "counterpart_probe_ip": counterpart_probe_ip,
            "counterpart_probe_mac": counterpart_probe_mac,
            "duration": parameters.duration
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


    def send_probe_coex_stop(self, probe_id, msm_id_to_stop, silent = False):
        json_coex_stop = {
            "handler": "coex",
            "command": "stop",
            "payload": {
                "msm_id": msm_id_to_stop,
                "silent": silent
            }
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_id, complete_command=json.dumps(json_coex_stop))


    def probes_preparer_to_measurements(self, new_measurement : MeasurementModelMongo):
        if new_measurement._id is None:
            new_measurement.assign_id()
        measurement_id = str(new_measurement._id)

        coex_parameters = self.get_default_coex_parameters()
        coex_parameters = self.override_default_parameters(coex_parameters, new_measurement.coexisting_application)
        if coex_parameters is None:
            return None, None, None
        coexisting_application = CoexistingApplicationModelMongo.cast_dict_in_CoexistingApplicationModelMongo(coex_parameters.copy())

        source_coex_probe_ip, source_coex_probe_mac = self.ask_probe_ip_mac(coexisting_application.source_probe)
        if (source_coex_probe_ip is None):
            print(f"Coex_Coordinator: Warning -> No response from coex client probe: {coexisting_application.source_probe}. -> NO COEXISTING APPLICATION TRAFFIC")
            return "Error", f"No response from client probe: {coexisting_application.source_probe}", "Reponse Timeout"
        
        dest_coex_probe_ip, dest_coex_probe_mac = self.ask_probe_ip_mac(coexisting_application.dest_probe)
        if dest_coex_probe_ip is None:
            print(f"Coex_Coordinator: No response from coex server probe: {coexisting_application.dest_probe}. -> NO COEXISTING APPLICATION TRAFFIC")
            return "Error", f"No response from server probe: {new_measurement.dest_probe}", "Reponse Timeout"
        
        if coexisting_application.delay_start != 0: # IF HAS BEEN SETTED A DELAY_START... then, we must wait
            print(f"Coex_Coordinator: coex traffic delayed of {str(coexisting_application.delay_start)}s")
            time.sleep(coexisting_application.delay_start) # I can do this, because all of this code is run by another thread respect to the main
        
        coexisting_application.source_probe_ip = source_coex_probe_ip
        coexisting_application.dest_probe_ip = dest_coex_probe_ip

        #new_measurement.coexisting_application.source_probe_ip = source_coex_probe_ip
        #new_measurement.dest_probe_ip = dest_coex_probe_ip
        new_measurement.coexisting_application = coexisting_application.to_dict() #CoexistingApplicationModelMongo.cast_dict_in_CoexistingApplicationModelMongo(coex_parameters.copy())
        self.queued_measurements[measurement_id] = new_measurement
        
        self.events_received_ack_from_probe_sender[measurement_id] = [threading.Event(), None]
        self.send_probe_coex_conf(probe_sender = coexisting_application.dest_probe, msm_id = measurement_id, role="Server",
                                  parameters = coexisting_application, counterpart_probe_ip=coexisting_application.source_probe_ip,
                                  counterpart_probe_mac = source_coex_probe_mac)

        self.events_received_ack_from_probe_sender[measurement_id][0].wait(timeout = 5)
        # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK FROM DEST_PROBE (COEX INITIATOR)

        probe_server_conf_message = self.events_received_ack_from_probe_sender[measurement_id][1]
        if probe_server_conf_message == "OK":
            self.events_received_ack_from_probe_sender[measurement_id] = [threading.Event(), None]
            self.send_probe_coex_conf(probe_sender = coexisting_application.source_probe, msm_id = measurement_id, role="Client",
                                      parameters = coexisting_application, counterpart_probe_ip = coexisting_application.dest_probe_ip,
                                      counterpart_probe_mac = dest_coex_probe_mac)
            self.events_received_ack_from_probe_sender[measurement_id][0].wait(timeout = 5)
            # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK FROM SOURCE_PROBE (COEX INITIATOR)
            probe_client_conf_message = self.events_received_ack_from_probe_sender[measurement_id][1]
            if probe_client_conf_message == "OK":
                self.queued_measurements[measurement_id] = new_measurement
                self.events_received_ack_from_probe_sender[measurement_id] = [threading.Event(), None]
                self.send_probe_coex_start(probe_id = coexisting_application.source_probe, msm_id = measurement_id)
                self.events_received_ack_from_probe_sender[measurement_id][0].wait(timeout = 60)
                # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK START FROM SOURCE_PROBE (COEX INITIATOR)
                probe_client_start_message = self.events_received_ack_from_probe_sender[measurement_id][1]
                if probe_client_start_message == "OK":
                    #inserted_measurement_id = self.mongo_db.insert_measurement(measure = new_measurement)
                    measure_has_been_updated = self.mongo_db.replace_measurement(measurement_id = measurement_id, measure = new_measurement)
                    if measure_has_been_updated is None:
                        print(f"Coex_Coordinator: can't update coex. Error while updating coex measurement on Mongo")
                    return "OK", new_measurement.to_dict(), None
                
                # Sending stop to the server probe, otherwise it will remain BUSY
                self.send_probe_coex_stop(probe_id=coexisting_application.dest_probe, msm_id_to_stop=measurement_id) 
                if probe_client_start_message is not None:
                    print(f"Preparer coex: awaked from client start NACK -> {probe_client_start_message}")
                    return "Error", f"Probe |{coexisting_application.source_probe}| says: {probe_server_conf_message}", ""      
                else:
                    print(f"Preparer coex: No response from probe -> |{coexisting_application.source_probe}")
                    return "Error", f"No response from Probe: {coexisting_application.source_probe}" , "Response Timeout"
            
            # Sending stop to the server probe, otherwise it will remain BUSY
            self.send_probe_coex_stop(probe_id=coexisting_application.dest_probe, msm_id_to_stop=measurement_id)
            if probe_client_conf_message is not None:
                print(f"Preparer coex: awaked from client conf NACK -> {probe_client_conf_message}")
                
                return "Error", f"Probe |{coexisting_application.source_probe}| says: {probe_client_conf_message}", ""      
            else:
                print(f"Preparer coex: No response from probe -> |{coexisting_application.source_probe}")
                # Sending stop to the server probe, otherwise it will remain BUSY
                self.send_probe_coex_stop(probe_id=coexisting_application.dest_probe, msm_id_to_stop=measurement_id) 
                return "Error", f"No response from Probe: {coexisting_application.source_probe}" , "Response Timeout"
        elif probe_server_conf_message is not None:
            print(f"Preparer coex: awaked from server conf NACK -> {probe_server_conf_message}")
            return "Error", f"Probe |{coexisting_application.dest_probe}| says: {probe_server_conf_message}", ""            
        else:
            print(f"Preparer coex: No response from probe -> |{coexisting_application.dest_probe}")
            return "Error", f"No response from Probe: {coexisting_application.dest_probe}" , "Response Timeout"


    def coex_measurement_stopper(self, msm_id_to_stop : str):
        if msm_id_to_stop not in self.queued_measurements:
            measure_from_db : MeasurementModelMongo = self.mongo_db.find_measurement_by_id(measurement_id=msm_id_to_stop)
            if isinstance(measure_from_db, ErrorModel):
                return "Error", measure_from_db.error_description, measure_from_db.error_cause
            self.queued_measurements[msm_id_to_stop] = measure_from_db

        if self.coex_stop_ack_number.get(msm_id_to_stop, 0) == 2: # This return "OK" in case the coex traffic is automatic ended
            return "OK", f"Coexistring Application traffic for {msm_id_to_stop}, -> STOPPED", None
        
        measurement_to_stop : MeasurementModelMongo = self.queued_measurements[msm_id_to_stop]
        coex_params = measurement_to_stop.coexisting_application

        if ('source_probe_ip' not in coex_params) or ('dest_probe_ip' not in coex_params):
            return None, None, None

        coexisting_application = CoexistingApplicationModelMongo.cast_dict_in_CoexistingApplicationModelMongo(measurement_to_stop.coexisting_application)

        self.events_stop_probe_ack[msm_id_to_stop] = [threading.Event(), None]
        self.send_probe_coex_stop(probe_id = coexisting_application.dest_probe, msm_id_to_stop = msm_id_to_stop)
        self.events_stop_probe_ack[msm_id_to_stop][0].wait(5)
        # ------------------------------- WAIT FOR RECEIVE AN ACK/NACK -------------------------------
        stop_event_message = self.events_stop_probe_ack[msm_id_to_stop][1]
        if stop_event_message == "OK":
            self.events_stop_probe_ack[msm_id_to_stop] = [threading.Event(), None]
            already_received_stop_ack_from_source_probe = self.coex_stop_ack_number.get(msm_id_to_stop, False)
            self.send_probe_coex_stop(probe_id = coexisting_application.source_probe, msm_id_to_stop = msm_id_to_stop, silent = already_received_stop_ack_from_source_probe)
            self.events_stop_probe_ack[msm_id_to_stop][0].wait(5)
            stop_event_message = self.events_stop_probe_ack[msm_id_to_stop][1]
            if (stop_event_message == "OK") or (self.coex_stop_ack_number.get(msm_id_to_stop, False)):
                #if self.mongo_db.set_measurement_as_completed(msm_id_to_stop):
                #    print(f"Coex_Coordinator: measurement |{msm_id_to_stop}| setted as completed")
                #else:
                #    print(f"Coex_Coordinator: error while setting |completed| the measure --> |{msm_id_to_stop}|")
                return "OK", f"Coexistring Application traffic for {msm_id_to_stop}, -> STOPPED", None
            if stop_event_message is not None:
                return "Error", f"Probe |{coexisting_application.source_probe}| says: |{stop_event_message}|", "May be the coex traffic is already finished."
            return "Error", f"Can't stop the measurement -> |{msm_id_to_stop}|", f"No response from probe |{coexisting_application.source_probe}|"
        
        self.send_probe_coex_stop(probe_id = coexisting_application.source_probe, msm_id_to_stop = msm_id_to_stop, silent=True)
        #if self.mongo_db.set_measurement_as_completed(msm_id_to_stop):
        #    print(f"Coex_Coordinator: measurement |{msm_id_to_stop}| setted as completed")
        
        if stop_event_message is not None:
            return "Error", f"Probe |{coexisting_application.dest_probe}| says: |{stop_event_message}|", "May be the coex traffic is already finished."
        return "Error", f"Can't stop the measurement -> |{msm_id_to_stop}|", f"No response from probe |{coexisting_application.dest_probe}|"
    

    def get_default_coex_parameters(self) -> json:
        base_path = os.path.join(Path(__file__).parent)       
        cl = ConfigLoader(base_path= base_path, file_name = "default_parameters.yaml", KEY = COEX_KEY)
        json_default_config = cl.config if (cl.config is not None) else {}
        return json_default_config

    def override_default_parameters(self, json_config : dict, measurement_parameters : dict):
        json_overrided_config = json_config.copy()
        source_probe_coex = measurement_parameters.get("source_probe")
        dest_probe_coex = measurement_parameters.get("dest_probe")
        description = json_config.get("description")
        duration = json_config.get("duration")
        if source_probe_coex is None:
            print("Coex_Coordinator: Warning --> missing coex source probe --> No Coexisting Application Traffic")
            return None
        if dest_probe_coex is None:
            print("Coex_Coordinator: Warning --> missing coex dest probe --> No Coexisting Application Traffic")
            return None

        if (measurement_parameters is not None) and (isinstance(measurement_parameters, dict)):
            if ("trace_name" in measurement_parameters) and (measurement_parameters["trace_name"] is not None):
                json_overrided_config["trace_name"] = measurement_parameters["trace_name"]
                json_overrided_config['packets_number'] = None
                json_overrided_config['packets_size'] = None # json_config['packets_size']
                json_overrided_config['packets_rate'] = None
                json_overrided_config['socket_port'] = json_config['socket_port']
            else:
                if ('packets_number' in measurement_parameters):
                    json_overrided_config['packets_number'] = measurement_parameters['packets_number']
                if ('packets_size' in measurement_parameters):
                    json_overrided_config['packets_size'] = measurement_parameters['packets_size']
                if ('packets_rate' in measurement_parameters):
                    json_overrided_config['packets_rate'] = measurement_parameters['packets_rate']
            if ('socket_port' in measurement_parameters):
                    json_overrided_config['socket_port'] = measurement_parameters['socket_port']
            if ('delay_start' in measurement_parameters):
                    json_overrided_config['delay_start'] = measurement_parameters['delay_start']
        description = measurement_parameters.get("description", description)
        duration = measurement_parameters.get("duration", duration)

        json_overrided_config['duration'] = duration
        json_overrided_config['description'] = description
        json_overrided_config['source_probe'] = source_probe_coex
        json_overrided_config['dest_probe'] = dest_probe_coex
        return json_overrided_config