import json
from ina219Driver import Ina219Driver
from mqttModule.mqttClient import ProbeMqttClient

class EnergyController:
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function):
        self.mqtt_client = mqtt_client
        try:
            self.driverINA = Ina219Driver()
        except Exception as e:
            self.mqtt_client.publish_error(handler="energy", payload=str(e))
            print(f"{e}")
            return
        
        # Requests to commands_multiplexer
        registration_response = registration_handler_request_function(
            interested_command = "energy",
            handler = self.energy_command_handler)
        if registration_response != "OK" :
            self.mqtt_client.publish_error(handler="energy", payload=registration_response)
            print(f"EnergyController: registration handler failed. Reason -> {registration_response}")
        self.mqtt_client.publish_command_ACK(handler="energy", payload="OK")

        
    def energy_command_handler(self, command : str, payload: json):
        print(f"command -> {command} | payload-> {payload}")
        match command:
            case "check":
                if self.driverINA.ina219.is_device_present():
                    check_msg = "i2C INA219 Found"
                    self.mqtt_client.publish_command_ACK(handler="energy", payload=check_msg)
                else:
                    check_msg = "i2C INA219 Found"
                    self.mqtt_client.publish_command_NACK(handler="energy", payload=check_msg)
            case _:
                print(f"EnergyController: commant not known -> {command}")
        