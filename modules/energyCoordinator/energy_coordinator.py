import json
import cbor2, base64
import threading
from modules.mongoModule.mongoDB import MongoDB
from modules.mqttModule.mqtt_client import Mqtt_Client
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from modules.mongoModule.models.energy_result_model_mongo import EnergyResultModelMongo

class EnergyCoordinator:
    def __init__(self, 
                 mqtt_client : Mqtt_Client,
                 registration_handler_status_callback,
                 registration_handler_result_callback,
                 registration_measure_preparer_callback,
                 registration_measurement_stopper_callback,
                 mongo_db : MongoDB):
        self.mqtt_client = mqtt_client
        self.mongo_db = mongo_db
        self.queued_measurements = {}
        self.events_received_start_ack = {}
        self.events_received_stop_ack = {}

         # Requests to CommandsDemultiplexer
        registration_response = registration_handler_status_callback(
            interested_status = "energy",
            handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"EnergyCoordinator: registered handler for status -> energy")
        else:
            print(f"EnergyCoordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to CommandsDemultiplexer
        registration_response = registration_handler_result_callback(
            interested_result = "energy",
            handler = self.handler_received_result)
        if registration_response == "OK" :
            print(f"EnergyCoordinator: registered handler for result -> energy")
        else:
            print(f"EnergyCoordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Probes-Preparer registration
        registration_response = registration_measure_preparer_callback(
            interested_measurement_type = "energy",
            preparer_callback = self.probes_preparer_to_measurements)
        if registration_response == "OK" :
            print(f"EnergyCoordinator: registered prepaper for measurements type -> energy")
        else:
            print(f"EnergyCoordinator: registration preparer failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Measurement-Stopper registration
        registration_response = registration_measurement_stopper_callback(
            interested_measurement_type = "energy",
            stopper_method_callback = self.energy_measurement_stopper)
        if registration_response == "OK" :
            print(f"EnergyCoordinator: registered measurement stopper for measurements type -> energy")
        else:
            print(f"EnergyCoordinator: registration measurement stopper failed. Reason -> {registration_response}")
        
    def handler_error_messages(self, probe_sender, payload : json):
        print(f"EnergyCoordinator: received error msg from |{probe_sender}| --> |{payload}|")
    
    def handler_received_status(self, probe_sender, type, payload):
        msm_id = payload["msm_id"] if ("msm_id" in payload) else None
        match type:
            case "ACK":
                command_executed_on_probe = payload["command"]
                match command_executed_on_probe:
                    case "check":
                        print(f"EnergyCoordinator: received ACK related to |check| from |{probe_sender}|")
                    case "start":
                        if msm_id is None:
                            print(f"EnergyCoordinator: received ACK related to |start| from |{probe_sender}| WITHOUT msm_id")
                            return
                        print(f"EnergyCoordinator: received ACK related to |start| from |{probe_sender}| , msm_id -> |{msm_id}|")
                        self.events_received_start_ack[msm_id][1] = "OK"
                        self.events_received_start_ack[msm_id][0].set()
                    case "stop":
                        if msm_id is None:
                            print(f"EnergyCoordinator: received ACK related to |stop| from |{probe_sender}| WITHOUT msm_id")
                            return
                        self.events_received_stop_ack[msm_id][1] = "OK"
                        self.events_received_stop_ack[msm_id][0].set()
                        print(f"EnergyCoordinator: received ACK related to |stop| from |{probe_sender}| , msm_id -> |{msm_id}|\nDA memorizzare nel db la timeseries")
            case "NACK":
                failed_command = payload["command"]
                reason = payload["reason"]
                print(f"EnergyCoordinator: NACK from probe -> |{probe_sender}| , command -> |{failed_command}| , reason -> |{reason}| , msm_id -> |{msm_id}|")
                match failed_command:
                    case "start":
                        if msm_id is not None:
                            self.events_received_start_ack[msm_id][1] = reason
                            self.events_received_start_ack[msm_id][0].set()
                    case "stop":
                        if msm_id is not None:
                            self.events_received_stop_ack[msm_id][1] = reason
                            self.events_received_stop_ack[msm_id][0].set()

    def handler_received_result(self, probe_sender, result: json):
        msm_id = result["msm_id"] if ("msm_id" in result) else None
        if msm_id is None:
            print(f"EnergyCoordinator: received result from |{probe_sender}| without measure id. -> IGNORE")
            return
        c_data_b64 = result["c_data_b64"] if ("c_data_b64" in result) else None
        if c_data_b64 is None:
            print(f"EnergyCoordinator: received result from |{probe_sender}| without data , measure_id -> {msm_id} -> IGNORE")
            return
        c_data = base64.b64decode(c_data_b64)
        timeseries = cbor2.loads(c_data)

        duration = result["duration"]
        energy = result["energy"]
        byte_tx = result["byte_tx"]
        byte_rx = result["byte_rx"]

        energy_result = EnergyResultModelMongo(msm_id = msm_id, timeseries = timeseries,
                                               energy=energy, byte_tx=byte_tx, byte_rx=byte_rx,
                                               duration=duration)
        energy_result_id = self.mongo_db.insert_energy_result(result = energy_result)
        if energy_result_id is not None:
            if self.mongo_db.update_results_array_in_measurement(msm_id = msm_id):
                print(f"EnergyCoordinator: updated document linking in measure: |{msm_id}|")
            if self.mongo_db.set_measurement_as_completed(msm_id):
                print(f"EnergyCoordinator: measurement |{msm_id}| completed ")
        else:
            print(f"EnergyCoordinator: error while storing result |{energy_result_id}|")
    
    
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
        # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK FROM SOURCE_PROBE
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


    def energy_measurement_stopper(self, msm_id_to_stop : str):
        if msm_id_to_stop not in self.queued_measurements:
            return "Error", "Unknown measurement in Energy Coordinator", "May be wrong type?"
        queued_measurement : MeasurementModelMongo = self.queued_measurements[msm_id_to_stop]
        print(f"energy_measurement_stopper()")

        json_energy_stop = {
            "handler": "energy",
            "command": "stop",
            "payload": {
                "msm_id": msm_id_to_stop
            }
        }
        self.events_received_stop_ack[msm_id_to_stop] = [threading.Event(), None]
        self.mqtt_client.publish_on_command_topic(probe_id = queued_measurement.source_probe,
                                                  complete_command=json.dumps(json_energy_stop))
        self.events_received_stop_ack[msm_id_to_stop][0].wait(timeout = 5)
        # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK FROM SOURCE_PROBE
        stop_event_message = self.events_received_stop_ack[msm_id_to_stop][1]
        if stop_event_message == "OK":
            return "OK", f"Measurement {msm_id_to_stop} stopped", None
        elif stop_event_message is not None:
            print(f"Measurement stoppper: awaked from probe energy NACK -> |{stop_event_message}|")
            return "Error", f"Probe |{queued_measurement.source_probe}| says: |{stop_event_message}|", ""
        else:
            print(f"Measurement stoppper: No response from probe -> |{queued_measurement.source_probe}")
            return "Error", f"No response from Probe: |{queued_measurement.source_probe}|" , "Response Timeout"