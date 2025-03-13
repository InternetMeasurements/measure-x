import os
from pathlib import Path
import json
import time
import threading
from datetime import datetime as dt
from modules.mqttModule.mqtt_client import Mqtt_Client
from modules.configLoader.config_loader import ConfigLoader, PING_KEY
from bson import ObjectId
from modules.mongoModule.mongoDB import MongoDB, SECONDS_OLD_MEASUREMENT
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from modules.mongoModule.models.coex_result_model_mongo import CoexResultModelMongo

class Ping_Coordinator:

    def __init__(self, mqtt_client : Mqtt_Client, registration_handler_status_callback,
                 registration_handler_result_callback, registration_measure_preparer_callback,
                 ask_probe_ip_callback, registration_measurement_stopper_callback,
                 mongo_db : MongoDB):
        self.mqtt_client = mqtt_client
        self.mongo_db = mongo_db
        self.ask_probe_ip = ask_probe_ip_callback
        self.events_received_ack_from_probe_sender = {}
        self.events_received_stop_ack = {}
        self.queued_measurements = {}

        # Requests to commands_multiplexer: handler STATUS registration
        registration_response = registration_handler_status_callback( interested_status = "coex",
                                                             handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"Ping_Coordinator: registered handler for status -> coex")
        else:
            print(f"Ping_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: handler RESULT registration
        registration_response = registration_handler_result_callback(interested_result = "coex",
                                                            handler = self.handler_received_result)
        if registration_response == "OK" :
            print(f"Ping_Coordinator: registered handler for result -> coex")
        else:
            print(f"Ping_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Probes-Preparer registration
        registration_response = registration_measure_preparer_callback(
            interested_measurement_type = "coex",
            preparer_callback = self.probes_preparer_to_measurements)
        if registration_response == "OK" :
            print(f"Ping_Coordinator: registered prepaper for measurements type -> coex")
        else:
            print(f"Ping_Coordinator: registration preparer failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Measurement-Stopper registration
        registration_response = registration_measurement_stopper_callback(
            interested_measurement_type = "coex",
            stopper_method_callback = self.ping_measurement_stopper)
        if registration_response == "OK" :
            print(f"Ping_Coordinator: registered measurement stopper for measurements type -> coex")
        else:
            print(f"Ping_Coordinator: registration measurement stopper failed. Reason -> {registration_response}")


    def handler_received_status(self, probe_sender, type, payload : json):
        msm_id = payload["msm_id"] if ("msm_id" in payload) else None
        command = payload["command"] if ("command" in payload) else None
        match type:
            case "ACK":
                if command == "start":
                    self.events_received_ack_from_probe_sender[msm_id][1] = "OK"
                    self.events_received_ack_from_probe_sender[msm_id][0].set()
                elif command == "stop":
                    if msm_id is None:
                        print(f"Ping_Coordinator: received |stop| ACK from probe |{probe_sender}| wihout measure_id")
                        return
                    if msm_id in self.events_received_stop_ack:
                        self.events_received_stop_ack[msm_id][1] = "OK"
                        self.events_received_stop_ack[msm_id][0].set()
                print(f"Ping_Coordinator: received ACK from probe |{probe_sender}| , command -> |{command}|")
            case "NACK":
                reason = payload['reason']
                if command == "start":
                    if msm_id in self.events_received_ack_from_probe_sender:
                        self.events_received_ack_from_probe_sender[msm_id][1] = reason
                        self.events_received_ack_from_probe_sender[msm_id][0].set()
                elif command == "stop":
                    if msm_id in self.events_received_stop_ack:
                        self.events_received_stop_ack[msm_id][1] = reason
                        self.events_received_stop_ack[msm_id][0].set()
                print(f"Ping_Coordinator: probe |{probe_sender}| , command: |{command}| -> NACK, reason -> {reason}")
            case _:
                print(f"Ping_Coordinator: received unkown type message -> |{type}|")


    def handler_received_result(self, probe_sender, result: json):
        measure_id = result['msm_id'] if ('msm_id' in result) else None
        if measure_id is None:
            print("Ping_Coordinator: received result wihout measure_id -> IGNORED")
            return
        
        if ((time.time() - result["timestamp"]) < SECONDS_OLD_MEASUREMENT):
            if self.store_measurement_result(result = result):
                print(f"Ping_Coordinator: complete the measurement store and update -> {measure_id}")
        else:
            print(f"Ping_Coordinator: ignored result. Reason: expired measurement -> {measure_id}")


    def send_probe_coex_start(self, probe_sender, json_payload):
        json_ping_start = {
            "handler": "coex",
            "command": "start",
            "payload": json_payload
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_ping_start))

    def send_probe_coex_stop(self, probe_id, msm_id_to_stop):
        json_ping_stop = {
            "handler": "coex",
            "command": "stop",
            "payload": {
                "msm_id": msm_id_to_stop
            }
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_id, complete_command=json.dumps(json_ping_stop))

    
    def store_measurement_result(self, result : json) -> bool:
        coex_result = CoexResultModelMongo()
        result_id = str(self.mongo_db.insert_result(result = coex_result))
        if result_id is not None:
            msm_id = result["msm_id"]
            print(f"Ping_Coordinator: result |{result_id}| stored in db")
            if self.mongo_db.update_results_array_in_measurement(msm_id):
                print(f"Ping_Coordinator: updated document linking in measure: |{msm_id}|")
                if self.mongo_db.set_measurement_as_completed(msm_id):
                    self.print_summary_result(measurement_result = result)
                    return True
        print(f"Ping_Coordinator: error while storing result |{result_id}|")
        return False


    def probes_preparer_to_measurements(self, new_measurement : MeasurementModelMongo):
        new_measurement.assign_id()
        measurement_id = str(new_measurement._id)

        ping_parameters = self.get_default_ping_parameters()
        ping_parameters = self.override_default_parameters(ping_parameters, new_measurement.parameters)
        new_measurement.parameters = ping_parameters.copy()

        if new_measurement.source_probe_ip is None or new_measurement.source_probe_ip == "":
            source_probe_ip = self.ask_probe_ip(new_measurement.source_probe)
            if source_probe_ip is None:
                return "Error", f"No response from probe: {new_measurement.source_probe}", "Reponse Timeout"
        
        dest_probe_ip = None # This IP is that of the "machine" that receive the ping message, not the ping initiator!
        if (new_measurement.dest_probe != None) and (new_measurement.dest_probe != ""): # If those are both false, then the ping dest is another probe
            dest_probe_ip = self.ask_probe_ip(new_measurement.dest_probe)
        else:
            dest_probe_ip = new_measurement.dest_probe_ip
        if dest_probe_ip is None:
            return "Error", f"No response from probe: {new_measurement.dest_probe}", "Reponse Timeout"
        
        json_start_payload = {
                "destination_ip": dest_probe_ip,
                "msm_id": measurement_id,
                "packets_number": ping_parameters["packets_number"],
                "packets_size": ping_parameters["packets_size"] }
        
        self.events_received_ack_from_probe_sender[measurement_id] = [threading.Event(), None]
        self.send_probe_ping_start(probe_sender = new_measurement.source_probe, json_payload=json_start_payload)

        self.events_received_ack_from_probe_sender[measurement_id][0].wait(timeout = 5)
        # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK FROM SENDER_PROBE (PING INITIATOR)

        probe_sender_event_message = self.events_received_ack_from_probe_sender[measurement_id][1]
        if probe_sender_event_message == "OK": # If the ping start succeded, then...
            new_measurement.source_probe_ip = source_probe_ip
            new_measurement.dest_probe_ip = dest_probe_ip
            inserted_measurement_id = self.mongo_db.insert_measurement(measure = new_measurement)
            if inserted_measurement_id is None:
                print(f"Ping_Coordinator: can't start ping. Error while storing ping measurement on Mongo")
                return "Error", "Can't send start! Error while inserting measurement ping in mongo", "MongoDB Down?"
            self.queued_measurements[measurement_id] = new_measurement
            return "OK", new_measurement.to_dict(), None
        elif probe_sender_event_message is not None:
            print(f"Preparer ping: awaked from server conf NACK -> {probe_sender_event_message}")
            return "Error", f"Probe |{new_measurement.source_probe}| says: {probe_sender_event_message}", "State BUSY"            
        else:
            print(f"Preparer ping: No response from probe -> |{new_measurement.source_probe}")
            return "Error", f"No response from Probe: {new_measurement.source_probe}" , "Response Timeout"
        

    def ping_measurement_stopper(self, msm_id_to_stop : str):
        if msm_id_to_stop not in self.queued_measurements:
            return "Error", f"Unknown ping measurement |{msm_id_to_stop}|", "May be not started"
        measurement_to_stop : MeasurementModelMongo = self.queued_measurements[msm_id_to_stop]
        self.events_received_stop_ack[msm_id_to_stop] = [threading.Event(), None]
        self.send_probe_ping_stop(probe_id = measurement_to_stop.source_probe, msm_id_to_stop = msm_id_to_stop)
        self.events_received_stop_ack[msm_id_to_stop][0].wait(5)
        # ------------------------------- WAIT FOR RECEIVE AN ACK/NACK -------------------------------
        if self.mongo_db.set_measurement_as_failed_by_id(msm_id_to_stop):
            print(f"Ping_Coordinator: measurement |{msm_id_to_stop}| setted as failed")
        stop_event_message = self.events_received_stop_ack[msm_id_to_stop][1]
        if stop_event_message == "OK":
            return "OK", f"Measurement {msm_id_to_stop} stopped", None
        if stop_event_message is not None:
            return "Error", f"Probe |{measurement_to_stop.source_probe}| says: |{stop_event_message}|", ""
        return "Error", f"Can't stop the measurement -> |{msm_id_to_stop}|", f"No response from probe |{measurement_to_stop.source_probe}|"
    

    def get_default_ping_parameters(self) -> json:
        base_path = os.path.join(Path(__file__).parent)       
        cl = ConfigLoader(base_path= base_path, file_name = "default_parameters.yaml", KEY = PING_KEY)
        json_default_config = cl.config if (cl.config is not None) else {}
        return json_default_config

    def override_default_parameters(self, json_config, measurement_parameters):
        json_overrided_config = json_config
        if (measurement_parameters is not None) and (isinstance(measurement_parameters, dict)):
            if ('packets_number' in measurement_parameters):
                json_overrided_config['packets_number'] = measurement_parameters['packets_number']
            if ('packets_size' in measurement_parameters):
                json_overrided_config['packets_size'] = measurement_parameters['packets_size']
        return json_overrided_config