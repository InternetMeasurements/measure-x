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
        self.last_probe_ntp_server_ip = None
        self._continue = False

        self.wait_for_set_coordinator_ip = wait_for_set_coordinator_ip

        # Requests to commands_demultiplexer
        registration_response = registration_handler_request_function(
            interested_command = "aoi",
            handler = self.aoi_command_handler)
        if registration_response != "OK" :
            print(f"AoIController: registration handler failed. Reason -> {registration_response}")


    def aoi_command_handler(self, command : str, payload: json):
         msm_id = payload["msm_id"] if "msm_id" in payload else None
         if msm_id is None:
             self.send_aoi_NACK(failed_command=command, error_info="No measurement_id provided")
             return
         match command:
            case "start":
                if not shared_state.set_probe_as_ready():
                    self.send_aoi_NACK(failed_command=command, error_info="PROBE BUSY", msm_id=msm_id)
                    return
                if shared_state.get_coordinator_ip() is None:
                    self.wait_for_set_coordinator_ip()
                    if shared_state.get_coordinator_ip() is None: # Necessary check for confirm the coordinator response of coordinator_ip
                        self.send_aoi_NACK(failed_command="start", error_info = "No response from coordinator. Missing coordinator ip for root service", msm_id=msm_id)
                        return
                self.prepare_probe_to_start_aoi_measure(msm_id=msm_id)
            case "disable_ntp_service":
                if not shared_state.set_probe_as_ready():
                    self.send_aoi_NACK(failed_command=command, error_info="PROBE BUSY", msm_id=msm_id)
                    return
                probe_ntp_server_ip = payload["probe_ntp_server"] if "probe_ntp_server" in payload else None
                if probe_ntp_server_ip is None:
                    self.send_aoi_NACK(failed_command=command, error_info="No probe-ntp-server provided", msm_id=msm_id)
                    return
                disable_msg = self.stop_ntpsec_service(msm_id = msm_id, probe_ntp_server_ip = probe_ntp_server_ip)
                if disable_msg == "OK":
                    self.send_aoi_ACK(successed_command = command, msm_id = msm_id)
                else:
                    self.send_aoi_NACK(failed_command = command, error_info = disable_msg, msm_id = msm_id)
            case "enable_ntp_service":
                if not shared_state.set_probe_as_ready():
                    self.send_aoi_NACK(failed_command=command, error_info="PROBE BUSY", msm_id=msm_id)
                    return
                enable_msg = self.start_ntpsec_service()
                if enable_msg == "OK":
                    self.send_aoi_ACK(successed_command = command, msm_id = msm_id)
                else:
                    self.send_aoi_NACK(failed_command = command, error_info = enable_msg, msm_id = msm_id)
            case "stop":
                msm_id = payload['msm_id']
                termination_message = self.stop_aoi_thread()
                if termination_message == "OK":
                    self.send_aoi_ACK(successed_command=command, msm_id=msm_id)
                else:
                    self.send_aoi_NACK(failed_command=command, error_info=termination_message)
                self.reset_vars()
                                

    def prepare_probe_to_start_aoi_measure(self, msm_id):
        self._continue = True
        self.aoi_thread = threading.Thread(target=self.run_aoi_measurement, args=(msm_id,))
        self.aoi_thread.start()


    def run_aoi_measurement(self, msm_id):
        result = subprocess.run( ['sudo', 'ntpdate', shared_state.get_coordinator_ip()], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            while(self._continue):
                current_time_utc = datetime.now(timezone.utc)
                print(f"Current UTC time: {current_time_utc}")
                threading.sleep(1)
                
        else:
            self.send_aoi_NACK(failed_command="start", error_info=result.stderr.decode('utf-8'), msm_id=msm_id)


    def stop_aoi_thread(self) -> str:
        if self.aoi_thread is None:
            return "Process NTPDATE not in Execution"
        self._continue = False
        return "OK"
    

    def stop_ntpsec_service(self, msm_id, probe_ntp_server_ip):
        stop_command = ["sudo", "systemctl" , "stop" , "ntpsec" ] #[ "sudo systemctl stop ntpsec" ]
        
        result = subprocess.run(stop_command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        if result.returncode != 0:
            stdout_stop_command = result.stdout.decode('utf-8')
            stderr_stop_command = result.stderr.decode('utf-8')
            return f"Error in stopping ntsec service. Return code: {result.returncode}. STDOUT: |{stdout_stop_command}|. STDERR: |{stderr_stop_command}|"
        self.last_probe_ntp_server_ip = probe_ntp_server_ip
        self.last_measurement_id = msm_id
        return "OK"
    
    
    def start_ntpsec_service(self):
        start_command = [ "sudo", "systemctl" , "restart" , "ntpsec" ] #[ "sudo systemctl start ntpsec" ]
        
        result = subprocess.run(start_command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        if result.returncode != 0:
            stdout_stop_command = result.stdout.decode('utf-8')
            return f"Error in staring ntsec service. Return code: {result.returncode}. STDOUT: {stdout_stop_command}"
        return "OK"
    

    def send_aoi_ACK(self, successed_command, msm_id = None):
        json_ack = { 
            "command" : successed_command,
            "msm_id" : msm_id
            }
        print(f"AoIController: ACK sending -> {json_ack}")
        self.mqtt_client.publish_command_ACK(handler='aoi', payload=json_ack) 


    def send_aoi_NACK(self, failed_command, error_info, msm_id = None):
        json_nack = {
            "command" : failed_command,
            "reason" : error_info,
            "msm_id" : msm_id
            }
        print(f"AoIController: NACK sending -> {json_nack}")
        self.mqtt_client.publish_command_NACK(handler='aoi', payload = json_nack) 


    def reset_vars(self):
        self.last_measurement_id = None
        self.aoi_thread = None
        self._continue = False