import json
from energyModule.ina219Driver import Ina219Driver, SYNC_OTII_PIN
from mqttModule.mqttClient import ProbeMqttClient

""" Class that implements the POWER CONSUMPTION measurement funcionality """
class EnergyController:
    def __init__(self, mqtt_client : ProbeMqttClient, 
                 registration_handler_request_function):
        self.mqtt_client = mqtt_client
        try:
            self.driverINA = Ina219Driver()
        except Exception as e:
            self.mqtt_client.publish_error(handler="energy", payload="No energy sensor provided")
            print(f"EnergyController: No energy sensor provided")
            return
        
        # Requests to commands_multiplexer
        registration_response = registration_handler_request_function(
            interested_command = "energy",
            handler = self.energy_command_handler)
        if registration_response != "OK" :
            self.mqtt_client.publish_error(handler = "energy", payload = registration_response)
            print(f"EnergyController: registration handler failed. Reason -> {registration_response}")

        
    def energy_command_handler(self, command : str, payload: json):
        print(f"EnergyController: command -> {command} | payload-> {payload}")
        match command:
            case "check":
                if self.INA_sensor_test() == "PASSED":
                    SYNC_OTII_PIN.on()
                    self.send_energy_ACK(successed_command="check")
                    SYNC_OTII_PIN.off()
                else:
                    self.send_energy_NACK(failed_command="start", error_info="INA219 NOT FOUND", measurement_id=msm_id)
            case "start":
                    msm_id = payload['msm_id'] if 'msm_id' in payload else None
                    if msm_id is None:
                        self.send_energy_NACK(failed_command="start", error_info="No measurement provided")
                        return
                    if self.INA_sensor_test() != "PASSED":
                        self.send_energy_NACK(failed_command="start", error_info="INA219 NOT FOUND", measurement_id=msm_id)
                        return
                    start_msg = self.driverINA.start_current_measurement(filename = msm_id)
                    if start_msg != "OK":
                        self.send_energy_NACK(failed_command="start", error_info=start_msg, measurement_id=msm_id)
                    else:
                        self.send_energy_ACK(successed_command="start", measurement_id=msm_id)
            case "stop":
                    msm_id = payload['msm_id'] if 'msm_id' in payload else None
                    if msm_id is None:
                        self.send_energy_NACK(failed_command="stop", error_info="No measurement provided")
                        return
                    stop_msg = self.driverINA.stop_current_measurement()
                    if stop_msg != "OK":
                        self.send_energy_NACK(failed_command="stop", error_info=stop_msg, measurement_id=msm_id)
                    else:
                        self.send_energy_ACK(successed_command="stop", measurement_id=msm_id)
            case _:
                print(f"EnergyController: unkown command -> {command}")
                self.send_energy_NACK(failed_command=command, error_info="Unknown command")

    def INA_sensor_test(self):
        test_sensor = self.driverINA.i2C_INA_check()
        return "PASSED" if test_sensor else "NOT PASSED"

    def send_energy_ACK(self, successed_command, measurement_id = None):
        json_ack = { 
            "command" : successed_command,
            "msm_id" : self.last_measurement_id if (measurement_id is None) else measurement_id
            }
        print(f"EnergyController: ACK sending -> {json_ack}")
        self.mqtt_client.publish_command_ACK(handler='energy', payload=json_ack) 
    
    def send_energy_NACK(self, failed_command, error_info, measurement_id = None):
        json_nack = {
            "command" : failed_command,
            "reason" : error_info,
            "msm_id" : self.last_measurement_id if (measurement_id is None) else measurement_id
            }
        print(f"EnergyController: NACK sending -> {json_nack}")
        self.mqtt_client.publish_command_NACK(handler='energy', payload = json_nack) 
        