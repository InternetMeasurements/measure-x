import threading, json
from modules.mqttModule.mqtt_client import Mqtt_Client
from modules.mongoModule.mongoDB import MongoDB, MeasurementModelMongo

class Age_of_Information_Coordinator:

    def __init__(self, mqtt_client : Mqtt_Client, registration_handler_error, registration_handler_status,
                 registration_handler_result, registration_measure_preparer, mongo_db : MongoDB):
        self.mqtt_client = mqtt_client
        self.mongo_db = mongo_db
        self.events_received_ack_from_probe_sender = None

        # Requests to commands_multiplexer: handler STATUS registration
        registration_response = registration_handler_status( interested_status = "aoi",
                                                             handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"AoI_Coordinator: registered handler for status -> aoi")
        else:
            print(f"AoI_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: handler RESULT registration
        registration_response = registration_handler_result(interested_result = "aoi",
                                                            handler = self.handler_received_result)
        if registration_response == "OK" :
            print(f"AoI_Coordinator: registered handler for result -> aoi")
        else:
            print(f"AoI_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Probes-Preparer registration
        registration_response = registration_measure_preparer(
            interested_measurement_type = "aoi",
            preparer = self.probes_preparer_to_measurements)
        if registration_response == "OK" :
            print(f"AoI_Coordinator: registered prepaper for measurements type -> aoi")
        else:
            print(f"AoI_Coordinator: registration preparer failed. Reason -> {registration_response}")


    def send_probe_aoi_start(self, probe_sender, json_payload):
        json_ping_start = {
            "handler": "aoi",
            "command": "start",
            "payload": json_payload
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_ping_start))


    def handler_received_result(self):
        return
    

    
    def handler_received_status(self, probe_sender, type, payload : json):
        match type:
            case "ACK":
                command_executed_on_probe = payload["command"]
                match command_executed_on_probe:
                    case "start":
                        measurement_id = payload["measurement_id"]
                        print(f"AoI_Coordinator: ACK from probe |{probe_sender}|->|start| , measurement_id -> |{measurement_id}|")
                        self.events_received_server_ack[measurement_id][1] = "OK"
                        self.events_received_server_ack[measurement_id][0].set()
                    case _:
                        print(f"AoI_Coordinator: ACK received for unkonwn AoI command -> {command_executed_on_probe}")
            case "NACK":
                failed_command = payload["command"]
                reason = payload['reason']
                measurement_id = payload["measurement_id"] if ('measurement_id' in payload) else None
                match failed_command:
                    case "start":
                            self.events_received_server_ack[measurement_id][1] = reason
                            self.events_received_server_ack[measurement_id][0].set()
                    case _:
                        print(f"AoI_Coordinator: NACK received for unkonwn AoI command -> {command_executed_on_probe}")
    


    def probes_preparer_to_measurements(self, new_measurement : MeasurementModelMongo):
        new_measurement.assign_id()
        measurement_id = new_measurement._id

        json_start_payload = {
                "destination_server_ip": new_measurement.dest_probe_ip,
                "msm_id": measurement_id }
        
        self.events_received_ack_from_probe_sender[measurement_id] = [threading.Event(), None]
        self.send_probe_aoi_start(probe_sender = new_measurement.source_probe, json_payload=json_start_payload)
        self.events_received_ack_from_probe_sender[measurement_id][0].wait(timeout = 5)

        probe_sender_event_message = self.events_received_ack_from_probe_sender[measurement_id][1]
        if probe_sender_event_message == "OK": # If the aoi configuration went good, then...
            inserted_measurement_id = self.mongo_db.insert_measurement(measure = new_measurement)
            if inserted_measurement_id is None:
                print(f"AoI_Coordinator: can't start aoi. Error while storing ping measurement on Mongo")
                return "Error", "Can't send start! Error while inserting measurement aoi in mongo", "MongoDB Down?"
            return "OK", new_measurement.to_dict(), None
        elif probe_sender_event_message is not None:
            print(f"Preparer AoI: awaked from server conf NACK -> {probe_sender_event_message}")
            return "Error", f"Probe |{new_measurement.source_probe}| says: {probe_sender_event_message}", "State BUSY"            
        else:
            print(f"Preparer AoI: No response from probe -> |{new_measurement.source_probe}")
            return "Error", f"No response from Probe: {new_measurement.source_probe}" , "Reponse Timeout"