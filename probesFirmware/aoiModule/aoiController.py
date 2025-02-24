import time
import json
import subprocess, threading, signal
import socket
from datetime import datetime, timezone
from mqttModule.mqttClient import ProbeMqttClient
from shared_resources import shared_state

""" Class that implements the AGE OF INFORMATION measurement funcionality """
class AgeOfInformationController:
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function, wait_for_set_coordinator_ip):
        
        self.mqtt_client = mqtt_client
        self.last_measurement_id = None
        self.last_probe_ntp_server_ip = None
        self.last_socket_port = None
        self.last_role = None
        self._continue = False
        self._continue_lock = threading.Lock()
        self.measure_socket = None

        self.aoi_thread = None
        self.aoi_server_thread = None

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
                if not shared_state.set_probe_as_busy():
                    self.send_aoi_NACK(failed_command=command, error_info="PROBE BUSY", msm_id=msm_id)
                    return
                if shared_state.get_coordinator_ip() is None:
                    self.wait_for_set_coordinator_ip()
                    if shared_state.get_coordinator_ip() is None: # Necessary check for confirm the coordinator response of coordinator_ip
                        self.send_aoi_NACK(failed_command="start", error_info = "No response from coordinator. Missing coordinator ip for root service", msm_id=msm_id)
                        return
                returned_msg = self.prepare_probe_to_start_aoi_measure(msm_id=msm_id)
                if returned_msg == "OK":
                    self.send_aoi_ACK(successed_command=command, msm_id=msm_id)
                else:
                    self.send_aoi_NACK(failed_command=command, error_info=returned_msg, msm_id=msm_id)
            case "stop":
                if shared_state.probe_is_ready():
                    self.send_aoi_NACK(failed_command=command, error_info="No AoI measurement in progress", msm_id=msm_id)
                    return
                if self.last_measurement_id != msm_id:
                    self.send_aoi_NACK(failed_command=command, 
                                           error_info="Measure_id MISMATCH: The provided measure_id does not correspond to the ongoing measurement", 
                                           msm_id=msm_id)
                    return
                if self.last_role == "Cient":
                    termination_message = self.stop_aoi_thread()
                    if termination_message == "OK":
                        self.send_aoi_ACK(successed_command=command, msm_id=msm_id)
                    else:
                        self.send_aoi_NACK(failed_command=command, error_info=termination_message)
                elif self.last_role == "Server":
                    # Dovrei aver creato un file di misurazioni, tipo quello dell'energy, da leggere ed inviare con MQTT al coordinator
                    # Ricordati di creare da entrambi i lati, server e client, i SOCKET sulla porta self.last_socker_port
                    print()
             
            case "disable_ntp_service":
                if not shared_state.set_probe_as_busy():
                    self.send_aoi_NACK(failed_command=command, error_info="PROBE BUSY", msm_id=msm_id)
                    return
                probe_ntp_server_ip = payload["probe_ntp_server"] if ("probe_ntp_server" in payload) else None
                if probe_ntp_server_ip is None:
                    self.send_aoi_NACK(failed_command=command, error_info="No probe-ntp-server provided", msm_id=msm_id)
                    shared_state.set_probe_as_ready()
                    return
                socket_port = payload["socket_port"] if ("socket_port" in payload) else None
                if socket_port is None:
                    self.send_aoi_NACK(failed_command=command, error_info="No socket port provided", msm_id=msm_id)
                    shared_state.set_probe_as_ready()
                    return
                role = payload["role"] if ("role" in payload) else None
                if socket_port is None:
                    self.send_aoi_NACK(failed_command=command, error_info="No role provided", msm_id=msm_id)
                    shared_state.set_probe_as_ready()
                    return
                disable_msg = self.stop_ntpsec_service()
                if disable_msg == "OK":
                    self.last_measurement_id = msm_id
                    self.last_probe_ntp_server_ip = probe_ntp_server_ip
                    self.last_socket_port = socket_port
                    self.last_role = role
                    socket_creation_msg = self.create_socket()
                    if socket_creation_msg == "OK":
                        self.send_aoi_ACK(successed_command = command, msm_id = msm_id)
                    else:
                        self.send_aoi_NACK(failed_command = command, error_info = socket_creation_msg, msm_id = msm_id)
                else:
                    self.send_aoi_NACK(failed_command = command, error_info = disable_msg, msm_id = msm_id)
                    shared_state.set_probe_as_ready()
            case "enable_ntp_service":
                role = payload["role"] if ("role" in payload) else None
                if role is None:
                    self.send_aoi_NACK(failed_command=command, error_info="No role provided", msm_id=msm_id)
                    return
                if role == "Server":
                    if not shared_state.set_probe_as_busy():
                        self.send_aoi_NACK(failed_command=command, error_info="PROBE BUSY", msm_id=msm_id)
                        return
                    socket_port = payload["socket_port"] if ("socket_port" in payload) else None
                    if socket_port is None:
                        self.send_aoi_NACK(failed_command=command, error_info="No socket_port provided", msm_id=msm_id)
                        shared_state.set_probe_as_ready()
                        return
                    enable_msg = self.start_ntpsec_service()
                    if enable_msg == "OK":
                        self.last_socket_port = socket_port
                        self.last_role = role
                        socket_creation_msg = self.create_socket()
                        if socket_creation_msg == "OK":
                            self.aoi_thread = threading.Thread(target=self.run_aoi_measurement, args=(msm_id,))
                            self.aoi_thread.start()
                            self.send_aoi_ACK(successed_command = command, msm_id = msm_id)
                    else:
                        self.send_aoi_NACK(failed_command = command, error_info = enable_msg, msm_id = msm_id)
                        shared_state.set_probe_as_ready()
                elif role == "Client":
                    if (not shared_state.probe_is_ready()) and (self.last_measurement_id == msm_id):
                        enable_msg = self.start_ntpsec_service()
                        if enable_msg == "OK":
                            self.send_aoi_ACK(successed_command = command, msm_id = msm_id)
                            shared_state.set_probe_as_ready()
                        else:
                            self.send_aoi_NACK(failed_command = command, error_info = enable_msg, msm_id = msm_id)
                    elif (not shared_state.probe_is_ready()):
                        self.send_aoi_NACK(failed_command=command, 
                                           error_info="Measure_id MISMATCH: The provided measure_id does not correspond to the ongoing measurement", 
                                           msm_id=msm_id) 
                    else:
                        self.send_aoi_NACK(failed_command=command, error_info="No AoI measurement in progress", msm_id = None)
                else:
                    self.send_aoi_NACK(failed_command = command, error_info = (f"Wrong role -> {role}"), msm_id = msm_id)
                
                
    def create_socket(self):
        try:
            self.measure_socket = socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.measure_socket.bind(shared_state.get_probe_ip(), self.last_socket_port)
            return "OK"
        except Exception as e:
            print(f"AoIController: exception while creating socket -> {str(e)}")
            return str(e)
                

    def prepare_probe_to_start_aoi_measure(self, msm_id):
        try:
            self.set_continue_value(True)
            self.aoi_thread = threading.Thread(target=self.run_aoi_measurement, args=(msm_id,))
            self.aoi_thread.start()
            return "OK"
        except Exception as e:
            returned_msg = (f"AoIController: exception while starting measure thread -> {str(e)}")
            print(returned_msg)
            return returned_msg


    def run_aoi_measurement(self, msm_id):
        if self.last_role == "Client":
            result = subprocess.run( ['sudo', 'ntpdate', self.last_probe_ntp_server_ip], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode == 0:
                while(self.get_continue_value()):
                        timestamp_message = {
                            "timestamp": time.perf_counter()
                        }
                        json_timestamp = json.dumps(timestamp_message)
                        self.sock.sendto(json_timestamp.encode(), (self.last_probe_ntp_server_ip, self.last_socket_port))
                        time.sleep(1)
            else:
                stderr_command = result.stderr.decode('utf-8')
                self.send_aoi_NACK(failed_command="start", error_info=stderr_command, msm_id=msm_id)
        elif self.last_role == "Server":
            try:
                data, addr = self.measure_socket.recvfrom(1024)
                receive_time = time.perf_counter()
                if self.last_update_time is not None:
                    aoi = receive_time - self.last_update_time
                    print(f"AoI: {aoi:.6f} secondi")
                
                self.last_update_time = receive_time
                print(f"Ricevuto: {data.decode()} da {addr}")
            except socket.error as e:
                print(f"Errore socket: {e}")

    def stop_aoi_thread(self) -> str:
        if self.aoi_thread is None:
            return "No AoI measure in progress"
        self.set_continue_value(False)
        self.aoi_thread.join()
        return "OK"
    

    def stop_ntpsec_service(self):
        stop_command = ["sudo", "systemctl" , "stop" , "ntpsec" ] #[ "sudo systemctl stop ntpsec" ]
        
        result = subprocess.run(stop_command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        if result.returncode != 0:
            stdout_stop_command = result.stdout.decode('utf-8')
            stderr_stop_command = result.stderr.decode('utf-8')
            return f"Error in stopping ntsec service. Return code: {result.returncode}. STDOUT: |{stdout_stop_command}|. STDERR: |{stderr_stop_command}|"
        return "OK"
    
    
    def start_ntpsec_service(self):
        start_command = [ "sudo", "systemctl" , "restart" , "ntpsec" ]
        
        result = subprocess.run(start_command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        stdout_stop_command = result.stdout.decode('utf-8')
        if result.returncode != 0:
            stderr_stop_command = result.stderr.decode('utf-8')
            return f"Error in staring ntsec service. Return code: {result.returncode}. STDOUT: |{stdout_stop_command}|. STDERR: |{stderr_stop_command}|"
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


    def get_continue_value(self):
        with self._continue_lock:
            return self._continue
    
    def set_continue_value(self, _continue):
        with self._continue_lock:
            self._continue = _continue

    def reset_vars(self):
        print("reset_vars()")
        self.last_measurement_id = None
        self.last_probe_ntp_server_ip = None
        self.last_socket_port = None
        self.last_role = None
        self.aoi_thread = None