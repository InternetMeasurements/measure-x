import json
from energyModule.ina219Driver import Ina219Driver, SYNC_OTII_PIN
from mqttModule.mqttClient import ProbeMqttClient

class EnergyController:
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function):
        self.mqtt_client = mqtt_client
        #try:
        self.driverINA = Ina219Driver()
        #except Exception as e:
        #    self.mqtt_client.publish_error(handler="energy", payload=str(e))
        #    print(f"{e}")
        #    return
        
        # Requests to commands_multiplexer
        registration_response = registration_handler_request_function(
            interested_command = "energy",
            handler = self.energy_command_handler)
        if registration_response != "OK" :
            self.mqtt_client.publish_error(handler="energy", payload=registration_response)
            print(f"EnergyController: registration handler failed. Reason -> {registration_response}")
        #self.mqtt_client.publish_command_ACK(handler="energy", payload="OK")

        
    def energy_command_handler(self, command : str, payload: json):
        print(f"EnergyController: command -> {command} | payload-> {payload}")
        match command:
            case "check":
                if self.driverINA.i2C_INA_check():
                    check_msg = "i2C INA219 Found"
                    SYNC_OTII_PIN.on()
                    self.mqtt_client.publish_command_ACK(handler="energy", payload=check_msg)
                    SYNC_OTII_PIN.off()
                else:
                    check_msg = "i2C INA219 NOT Found"
                    self.mqtt_client.publish_command_NACK(handler="energy", payload=check_msg)
            case "start":
                    start_msg = self.driverINA.start_current_measurement()
                    if start_msg != "OK":
                         self.mqtt_client.publish_command_NACK(handler="energy", payload=start_msg)
                    else:
                         self.mqtt_client.publish_command_ACK(handler="energy", payload=command)
            case "stop":
                    stop_msg = self.driverINA.stop_current_measurement()
                    if stop_msg != "OK":
                         self.mqtt_client.publish_command_NACK(handler="energy", payload=stop_msg)
                    else:
                         self.mqtt_client.publish_command_ACK(handler="energy", payload=command)
            case _:
                print(f"EnergyController: commant not known -> {command}")
        