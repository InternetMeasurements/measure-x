import json
import threading
from modules.mongoModule.mongoDB import MongoDB
from modules.mqttModule.mqtt_client import Mqtt_Client
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo

class EnergyCoordinator:
    def __init__(self, 
                 mqtt_client : Mqtt_Client,
                 registration_handler_status,
                 registration_handler_result,
                 registration_measure_preparer,
                 mongo_db : MongoDB):
        self.mqtt_client = mqtt_client
        self.mongo_db = mongo_db
        self.queued_measurements = {}
        self.events_received_start_ack = {}

         # Requests to CommandsDemultiplexer
        registration_response = registration_handler_status(
            interested_status = "energy",
            handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"EnergyCoordinator: registered handler for status -> energy")
        else:
            print(f"EnergyCoordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to CommandsDemultiplexer
        registration_response = registration_handler_result(
            interested_result = "energy",
            handler = self.handler_received_result)
        if registration_response == "OK" :
            print(f"EnergyCoordinator: registered handler for result -> energy")
        else:
            print(f"EnergyCoordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Probes-Preparer registration
        registration_response = registration_measure_preparer(
            interested_measurement_type = "energy",
            preparer = self.probes_preparer_to_measurements)
        if registration_response == "OK" :
            print(f"EnergyCoordinator: registered prepaper for measurements type -> energy")
        else:
            print(f"EnergyCoordinator: registration preparer failed. Reason -> {registration_response}")
        
    def handler_error_messages(self, probe_sender, payload : json):
        print(f"EnergyCoordinator: received error msg from |{probe_sender}| --> |{payload}|")
    
    def handler_received_status(self, probe_sender, type, payload):
        match type:
            case "ACK":
                command_executed_on_probe = payload["command"]
                measurement_id = payload["msm_id"] if ("msm_id" in payload) else None
                match command_executed_on_probe:
                    case "check":
                        print(f"EnergyCoordinator: received ACK related to |check| from |{probe_sender}|")
                    case "start":
                        if measurement_id is None:
                            print(f"EnergyCoordinator: received ACK related to |start| from {probe_sender} WITHOUT msm_id")
                            return
                        print(f"EnergyCoordinator:")
            case "NACK":
                failed_command = payload["command"]
                reason = payload["reason"]
                measurement_id = payload["msm_id"] if ("msm_id" in payload) else None
                print(f"EnergyCoordinator: NACK from probe ->|{probe_sender}| reason ->|{reason}| msm_id ->|{measurement_id}|")
                if measurement_id is not None:
                    self.events_received_start_ack[measurement_id][1] = reason
                    self.events_received_start_ack[measurement_id][0].set()

    def handler_received_result(self, probe_sender, result: json):
        print(f"EnergyCoordinator: result received from {probe_sender}")

    
    
    def send_check_i2C_command(self, probe_id):
        json_check_i2C_command = {
            "handler": "energy",
            "command": "check",
            "payload": {}
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_id, 
                                                  complete_command = json.dumps(json_check_i2C_command))
        
    def probes_preparer_to_measurements(self, new_measurement : MeasurementModelMongo):
        new_measurement.assign_id()
        measurement_id = str(new_measurement._id)
        self.events_received_start_ack[measurement_id] = [threading.Event(), None]
        self.queued_measurements[str(new_measurement._id)] = new_measurement

        json_iperf_start = {
            "handler": "energy",
            "command": "start",
            "payload": {
                "msm_id": measurement_id
            }
        }
        self.events_received_start_ack[measurement_id] = [threading.Event(), None]
        self.mqtt_client.publish_on_command_topic(probe_id = new_measurement.source_probe, complete_command = json.dumps(json_iperf_start))
        self.events_received_start_ack[measurement_id][0].wait(timeout = 5)
        # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK FROM DEST_PROBE
        probe_event_message = self.events_received_start_ack[measurement_id][1]
        if probe_event_message == "OK":
            measurement_id = self.mongo_db.insert_measurement(new_measurement)
            if (measurement_id is None):
                return "Error", "Can't store measure in Mongo! Error while inserting measurement energy in mongo", "MongoDB Down?"
            return "OK", new_measurement.to_dict(), None # By returning these arguments, it's possible to see them in the HTTP response
        elif probe_event_message is not None:
            print(f"Preparer energy: awaked from probe energy NACK -> {probe_event_message}")
            return "Error", f"Probe |{new_measurement.source_probe}| says: {probe_event_message}", ""
        else:
            print(f"Preparer energy: No response from probe -> |{new_measurement.source_probe}")
            return "Error", f"No response from Probe: {new_measurement.source_probe}" , "Response Timeout"

    def send_stop_command(self, probe_id, msm_id):
        json_energy_stop = {
            "handler": "energy",
            "command": "stop",
            "payload": {
                "msm_id": msm_id
            }
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_id,
                                                  complete_command=json.dumps(json_energy_stop))
    