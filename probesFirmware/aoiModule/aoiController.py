import json
import subprocess, threading, signal
from datetime import datetime, timezone
from mqttModule.mqttClient import ProbeMqttClient
from shared_resources import shared_state

""" Class that implements the AGE OF INFORMATION measurement funcionality """
class AgeOfInformationController:
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function, wait_for_set_coordinator_ip):
        
        self.mqtt_client = mqtt_client
        self.aoi_thread = None
        self.last_measurement_id = None
        self._continue = False

        self.wait_for_set_coordinator_ip = wait_for_set_coordinator_ip

        # Requests to commands_demultiplexer
        registration_response = registration_handler_request_function(
            interested_command = "aoi",
            handler = self.aoi_command_handler)
        if registration_response != "OK" :
            print(f"AoIController: registration handler failed. Reason -> {registration_response}")


    def aoi_command_handler(self, command : str, payload: json):
         match command:
            case "start":
                msm_id = payload['msm_id']
                if not shared_state.set_probe_as_ready():
                    self.send_aoi_NACK(failed_command="start", error_info="PROBE BUSY", measurement_id=msm_id)
                    return
                
                if shared_state.get_coordinator_ip() is None:
                    self.wait_for_set_coordinator_ip()
                    if shared_state.get_coordinator_ip() is None: # Necessary check for confirm the coordinator response of coordinator_ip
                        self.send_aoi_NACK(failed_command="start", error_info = "No response from coordinator. Missing coordinator ip for root service", measurement_id=msm_id)
                        return
                
                self.send_aoi_ACK(successed_command="start", measurement_id=msm_id)
                self._continue = True
                self.aoi_thread = threading.Thread(target=self.run_aoi_measurement, args=(msm_id))
                self.aoi_thread.start()
            case "stop":
                msm_id = payload['msm_id']
                termination_message = self.stop_aoi_thread()
                if termination_message == "OK":
                    self.send_aoi_ACK(successed_command=command, measurement_id=msm_id)
                else:
                    self.send_aoi_NACK(failed_command=command, error_info=termination_message)
                self.reset_vars()
                
                

    def run_aoi_measurement(self, msm_id):
        result = subprocess.run( ['sudo', 'ntpdate', shared_state.get_coordinator_ip()], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            while(self._continue):
                current_time_utc = datetime.now(timezone.utc)
                print(f"Current UTC time: {current_time_utc}")
                threading.sleep(1)
        else:
            self.send_aoi_NACK(failed_command="start", error_info=result.stderr.decode('utf-8'), measurement_id=msm_id)

    def stop_aoi_thread(self) -> str:
        if self.aoi_thread is None:
            return "Process NTPDATE not in Execution"
        self._continue = False
        return "OK"



    def send_aoi_ACK(self, successed_command, measurement_id = None):
        json_ack = { 
            "command" : successed_command,
            "measurement_id" : self.last_measurement_id if (measurement_id is None) else measurement_id
            }
        print(f"AoIController: ACK sending -> {json_ack}")
        self.mqtt_client.publish_command_ACK(handler='aoi', payload=json_ack) 
    
    def send_aoi_NACK(self, failed_command, error_info, measurement_id = None):
        json_nack = {
            "command" : failed_command,
            "reason" : error_info,
            "measurement_id" : self.last_measurement_id if (measurement_id is None) else measurement_id
            }
        print(f"AoIController: NACK sending -> {json_nack}")
        self.mqtt_client.publish_command_NACK(handler='aoi', payload = json_nack) 
    
    def reset_vars(self):
        self.last_measurement_id = None
        self.aoi_thread = None
        self._continue = False