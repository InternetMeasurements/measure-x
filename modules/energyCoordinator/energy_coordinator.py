import json
from modules.mongoModule.mongoDB import MongoDB
from modules.mqttModule.mqtt_client import Mqtt_Client

class EnergyCoordinator:
    def __init__(self, 
                 mqtt_client : Mqtt_Client,
                 registration_handler_error,
                 registration_handler_status,
                 registration_handler_result,
                 mongo_db : MongoDB):
        self.mqtt_client = mqtt_client
        self.mongo_db = mongo_db

        # Requests to CommandsDemultiplexer
        registration_response = registration_handler_error(
            interested_error = "energy",
            handler = self.handler_error_messages)
        if registration_response == "OK" :
            print(f"Energy_Coordinator: registered handler for error -> energy")
        else:
            print(f"Energy_Coordinator: registration handler failed. Reason -> {registration_response}")

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
            print(f"Energy_Coordinator: registered handler for result -> energy")
        else:
            print(f"EnergyCoordinator: registration preparer failed. Reason -> {registration_response}")
        
    def handler_error_messages(self, probe_sender, payload : json):
        print(f"EnergyCoordinator: received error msg from |{probe_sender}| --> |{payload}|")
    
    def handler_received_status(self, probe_sender, type, payload):
        print(f"Energy_Coordinator: status sender->|{probe_sender}| type->|{type}| payload->|{payload}|")

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
        
    def send_start_command(self, probe_id):
        json_energy_start = {
            "handler": "energy",
            "command": "start",
            "payload": {}
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_id,
                                                  complete_command=json.dumps(json_energy_start))
    
    def send_stop_command(self, probe_id):
        json_energy_stop = {
            "handler": "energy",
            "command": "stop",
            "payload": {}
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_id,
                                                  complete_command=json.dumps(json_energy_stop))
    