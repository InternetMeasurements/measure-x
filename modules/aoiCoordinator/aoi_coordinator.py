import threading, json
from modules.mqttModule.mqtt_client import Mqtt_Client
from modules.mongoModule.mongoDB import MongoDB, MeasurementModelMongo

class Age_of_Information_Coordinator:

    def __init__(self, mqtt_client : Mqtt_Client, registration_handler_error, registration_handler_status,
                 registration_handler_result, registration_measure_preparer,
                 ask_probe_ip, registration_measurement_stopper, mongo_db : MongoDB):
        self.mqtt_client = mqtt_client
        self.ask_probe_ip = ask_probe_ip
        self.mongo_db = mongo_db
        self.events_received_status_from_probe_sender = {}

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
        
        # Requests to commands_multiplexer: Measurement-Stopper registration
        registration_response = registration_measurement_stopper(
            interested_measurement_type = "aoi",
            stopper_method = self.aoi_measurement_stopper)
        if registration_response == "OK" :
            print(f"AoI_Coordinator: registered measurement stopper for measurements type -> aoi")
        else:
            print(f"AoI_Coordinator: registration measurement stopper failed. Reason -> {registration_response}")


    def send_probe_aoi_start(self, probe_sender, json_payload):
        json_ping_start = {
            "handler": "aoi",
            "command": "start",
            "payload": json_payload
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_ping_start))

    
    def send_disable_ntp_service(self, probe_sender, json_payload):
        json_ping_start = {
            "handler": "aoi",
            "command": "disable_ntp_service",
            "payload": json_payload
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_ping_start))


    def send_enable_ntp_service(self, probe_sender, json_payload):
        json_ping_start = {
            "handler": "aoi",
            "command": "enable_ntp_service",
            "payload": json_payload
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_ping_start))


        

    def handler_received_result(self):
        return
    

    
    def handler_received_status(self, probe_sender, type, payload : json):
        msm_id = payload["msm_id"] if "msm_id" in payload else None
        if msm_id is None:
            print(f"AoI_Coordinator: |{type}| from probe |{probe_sender}| -> No measure_id provided. IGNORE.")
            return
        match type:
            case "ACK":
                command_executed_on_probe = payload["command"]
                match command_executed_on_probe:
                    case "start":
                        print(f"AoI_Coordinator: ACK from probe |{probe_sender}|->|start| , measurement_id -> |{msm_id}|")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = "OK"
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "disable_ntp_service":
                        print(f"AoI_Coordinator: ACK from probe |{probe_sender}| , command: |{command_executed_on_probe}| , msm_id: |{msm_id}|")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = "OK"
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "enable_ntp_service":
                        print(f"AoI_Coordinator: ACK from probe |{probe_sender}| , command: |{command_executed_on_probe}| , msm_id: |{msm_id}|")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = "OK"
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case _:
                        print(f"AoI_Coordinator: ACK received for unkonwn AoI command -> {command_executed_on_probe}")
            case "NACK":
                failed_command = payload["command"]
                reason = payload['reason']
                match failed_command:
                    case "start":
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = reason
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "disable_ntp_service":
                        print(f"AoI_Coordinator: received NACK for {failed_command} -> reason: {reason}")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = reason
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "enable_ntp_service":
                        print(f"AoI_Coordinator: received NACK for {failed_command} -> reason: {reason}")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = reason
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case _:
                        print(f"AoI_Coordinator: NACK received for unkonwn AoI command -> {command_executed_on_probe}")
    

    def probes_preparer_to_measurements(self, new_measurement : MeasurementModelMongo):
        new_measurement.assign_id()
        msm_id = str(new_measurement._id)

        source_probe_ip = self.ask_probe_ip(new_measurement.source_probe)
        if source_probe_ip is None:
            return "Error", f"No response from client probe: {new_measurement.source_probe}", "Reponse Timeout"
        dest_probe_ip = self.ask_probe_ip(new_measurement.dest_probe)
        if dest_probe_ip is None:
            return "Error", f"No response from client probe: {new_measurement.dest_probe}", "Reponse Timeout"
        new_measurement.source_probe_ip = source_probe_ip
        new_measurement.dest_probe_ip = dest_probe_ip

        json_disable_ntp_service_payload = {
                "probe_ntp_server": new_measurement.dest_probe_ip,
                "msm_id": msm_id }
        
        self.events_received_status_from_probe_sender[msm_id] = [threading.Event(), None]
        self.send_disable_ntp_service(probe_sender = new_measurement.source_probe, json_payload=json_disable_ntp_service_payload)
        self.events_received_status_from_probe_sender[msm_id][0].wait(timeout = 5)        

        event_disable_msg = self.events_received_status_from_probe_sender[msm_id][1]
        if event_disable_msg == "OK":
            json_start_payload = { "msm_id": msm_id }

            self.events_received_status_from_probe_sender[msm_id] = [threading.Event(), None]
            self.send_probe_aoi_start(probe_sender = new_measurement.source_probe, json_payload=json_start_payload)
            self.events_received_status_from_probe_sender[msm_id][0].wait(timeout = 5)       

            event_start_msg = self.events_received_status_from_probe_sender[msm_id][1]
            if event_start_msg == "OK":
                inserted_measurement_id = self.mongo_db.insert_measurement(measure = new_measurement)
                if inserted_measurement_id is None:
                    print(f"AoI_Coordinator: can't start aoi. Error while storing ping measurement on Mongo")
                    return "Error", "Can't send start! Error while inserting measurement aoi in mongo", "MongoDB Down?"
                return "OK", new_measurement.to_dict(), None
            elif event_start_msg is not None:
                print(f"Preparer AoI: awaked from server conf NACK -> {event_start_msg}")
                return "Error", f"Probe |{new_measurement.source_probe}| says: {event_start_msg}", "State BUSY"
            else:
                print(f"Preparer AoI: No response from probe -> |{new_measurement.source_probe}")
                return "Error", f"No response from Probe: {new_measurement.source_probe}" , "Reponse Timeout"   
        elif event_disable_msg is not None:
            print(f"Preparer AoI: awaked from server conf NACK -> {event_disable_msg}")
            return "Error", f"Probe |{new_measurement.source_probe}| says: {event_disable_msg}", "State BUSY"            
        else:
            print(f"Preparer AoI: No response from probe -> |{new_measurement.source_probe}")
            return "Error", f"No response from Probe: {new_measurement.source_probe}" , "Reponse Timeout"
        
    
    def aoi_measurement_stopper(self):
        print("AoI_Coordinator: stopper()")        