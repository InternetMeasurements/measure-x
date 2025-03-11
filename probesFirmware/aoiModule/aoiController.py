import os, csv
import time, datetime
import json
import subprocess, threading, signal
import socket
import base64, cbor2, pandas as pd
from pathlib import Path
from mqttModule.mqttClient import ProbeMqttClient
from shared_resources import shared_state

DEFAULT_AoI_MEASUREMENT_FOLDER = "aoi_measurements"

class AgeOfInformationController:
    """ Class that implements the AGE OF INFORMATION measurement funcionality """
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function, wait_for_set_coordinator_ip):
        
        self.mqtt_client = mqtt_client
        self.last_measurement_id = None
        self.last_probe_ntp_server_ip = None
        self.last_probe_server_aoi = None
        self.last_socket_port = None
        self.last_role = None
        self.last_update_time = None
        self.stop_thread_event = threading.Event()
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
                if (not shared_state.probe_is_ready()): # If the probe has an on-going measurement...
                    if self.last_measurement_id != msm_id: # If this ongoing measurement is not the one mentioned in the command
                        self.send_aoi_NACK(failed_command=command, 
                                           error_info="PROBE BUSY", # This error info can be also a MISMATCH error, but in this case is the same
                                           msm_id=msm_id)
                        return
                    if shared_state.get_coordinator_ip() is None:
                        self.wait_for_set_coordinator_ip() # BLOCKING METHOD!
                        if shared_state.get_coordinator_ip() is None: # Necessary check for confirm the coordinator response of coordinator_ip
                            self.send_aoi_NACK(failed_command="start", error_info = "No response from coordinator. Missing coordinator ip for root service", msm_id=msm_id)
                            return

                    payload_size = payload['payload_size'] if ('payload_size' in payload) else None
                    if payload_size is None:
                        self.send_aoi_NACK(failed_command=command, error_info="No payload size provided. Force PROBE_READY", msm_id=msm_id)
                        shared_state.set_probe_as_ready()
                        return
                    
                    packets_rate = payload['packets_rate'] if ('packets_rate' in payload) else None
                    if packets_rate is None:
                        self.send_aoi_NACK(failed_command=command, error_info="No packets rate provided. Force PROBE_READY", msm_id=msm_id)
                        shared_state.set_probe_as_ready()
                        return
                    
                    returned_msg = self.submit_thread_to_aoi_measure(msm_id = msm_id, payload_size = payload_size,
                                                                     packets_rate = packets_rate)
                    if returned_msg == "OK":
                        self.aoi_thread.start()
                    else:
                        self.send_aoi_NACK(failed_command = command, error_info = returned_msg, msm_id = msm_id)
                else:
                    self.send_aoi_NACK(failed_command = command, error_info = "No AoI measurement in progress", msm_id = msm_id)
            case "stop":
                if shared_state.probe_is_ready():
                    self.send_aoi_NACK(failed_command = command, error_info = "No AoI measurement in progress", msm_id = msm_id)
                    return
                if self.last_measurement_id != msm_id:
                    self.send_aoi_NACK(failed_command=command, 
                                           error_info="Measure_id MISMATCH: The provided measure_id does not correspond to the ongoing measurement", 
                                           msm_id=msm_id)
                    return
                print("stopping...")
                termination_message = self.stop_aoi_thread()
                if termination_message == "OK":
                    self.send_aoi_ACK(successed_command=command, msm_id=msm_id)
                    if self.last_role == "Server":
                        self.reset_vars()
                else:
                    self.send_aoi_NACK(failed_command=command, error_info=termination_message)
                shared_state.set_probe_as_ready()

                    # Dovrei aver creato un file di misurazioni, tipo quello dell'energy, da leggere ed inviare con MQTT al coordinator
                    # Ricordati di creare da entrambi i lati, server e client, i SOCKET sulla porta self.last_socker_port
                
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
                if role is None:
                    self.send_aoi_NACK(failed_command=command, error_info="No role provided", msm_id=msm_id)
                    shared_state.set_probe_as_ready()
                    return
                last_probe_server_aoi = payload["probe_server_aoi"] if ("probe_server_aoi" in payload) else None
                if last_probe_server_aoi is None:
                    self.send_aoi_NACK(failed_command=command, error_info="No server aoi provided", msm_id=msm_id)
                    shared_state.set_probe_as_ready()
                    return
                disable_msg = self.stop_ntpsec_service()
                if disable_msg == "OK":
                    self.last_measurement_id = msm_id
                    self.last_probe_ntp_server_ip = probe_ntp_server_ip
                    self.last_probe_server_aoi = last_probe_server_aoi
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
                payload_size = payload['payload_size'] if ('payload_size' in payload) else None
                if role == "Server":
                    if not shared_state.set_probe_as_busy():
                        self.send_aoi_NACK(failed_command=command, error_info="PROBE BUSY", msm_id=msm_id)
                        return
                    socket_port = payload["socket_port"] if ("socket_port" in payload) else None
                    if socket_port is None:
                        self.send_aoi_NACK(failed_command=command, error_info="No socket_port provided", msm_id=msm_id)
                        shared_state.set_probe_as_ready()
                        return
                    if payload_size is None:
                        self.send_aoi_NACK(failed_command=command, error_info="No payload_size provided", msm_id=msm_id)
                        shared_state.set_probe_as_ready()
                        return
                    
                    socket_timeout = payload["socket_timeout"] if ("socket_timeout" in payload) else None
                    
                    enable_msg = self.start_ntpsec_service()
                    if enable_msg == "OK":
                        self.last_socket_port = socket_port
                        self.last_role = role
                        self.last_measurement_id = msm_id
                        socket_creation_msg = self.create_socket(socket_timeout)
                        if socket_creation_msg == "OK":
                            returned_msg = self.submit_thread_to_aoi_measure(msm_id = msm_id, payload_size=payload_size)
                            if returned_msg == "OK":
                                self.aoi_thread.start()
                                self.send_aoi_ACK(successed_command = command, msm_id = msm_id)
                            else:
                                self.send_aoi_NACK(failed_command = command, error_info = returned_msg, msm_id = msm_id)
                        else:
                            self.send_aoi_NACK(failed_command=command, error_info=socket_creation_msg, msm_id=msm_id)
                    else:
                        self.send_aoi_NACK(failed_command = command, error_info = enable_msg, msm_id = msm_id)
                        shared_state.set_probe_as_ready()
                elif role == "Client":
                    if self.last_measurement_id == msm_id:
                        enable_msg = self.start_ntpsec_service()
                        self.reset_vars()
                        if enable_msg == "OK":
                            self.send_aoi_ACK(successed_command = command, msm_id = msm_id)
                            #shared_state.set_probe_as_ready()
                        else:
                            self.send_aoi_NACK(failed_command = command, error_info = enable_msg, msm_id = msm_id)
                    elif self.last_measurement_id is None:
                        self.send_aoi_NACK(failed_command=command, error_info="No AoI measurement in progress", msm_id = None)
                    else:
                        self.send_aoi_NACK(failed_command=command, 
                                           error_info="Measure_id MISMATCH: The provided measure_id does not correspond to the ongoing measurement", 
                                           msm_id=msm_id) 
                else:
                    self.send_aoi_NACK(failed_command = command, error_info = (f"Wrong role -> {role}"), msm_id = msm_id)
                
                
    def create_socket(self, socket_timeout = None):
        try:
            self.measure_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.measure_socket.bind((shared_state.get_probe_ip(), self.last_socket_port))
            if self.last_role == "Server":
                if (socket_timeout is not None) and (socket_timeout > 0):
                    self.measure_socket.settimeout(socket_timeout)
                    print(f"AoIController: Opened socket on IP: |{shared_state.get_probe_ip()}| , port: |{self.last_socket_port}|")
                else:
                    print(f"AoIController: DEBUG -> Opened socket on IP: |{shared_state.get_probe_ip()}| , port: |{self.last_socket_port}|")
            #self.measure_socket.settimeout(10)
            return "OK"
        except socket.error as e:
            print(f"AoIController: Socket error while creating socket -> {str(e)}")
            return f"Socket error: {str(e)}"
        except Exception as e:
            print(f"AoIController: Exception while creating socket -> {str(e)}")
            self.measure_socket.close()
            return str(e)
                

    def submit_thread_to_aoi_measure(self, msm_id,  payload_size = None, packets_rate = None):
        try:
            self.aoi_thread = threading.Thread(target=self.run_aoi_measurement, args=(msm_id,payload_size,packets_rate,))
            return "OK"
        except Exception as e:
            returned_msg = (f"Exception while starting measure thread -> {str(e)}")
            print(f"AoIController: {returned_msg}")
            return returned_msg


    def run_aoi_measurement(self, msm_id, payload_size, packets_rate):
        if self.last_role == "Client":
            stderr_command = None
            try:
                if packets_rate is None:
                    raise Exception(f"AoIController: wrong packets_rate -> |{packets_rate}|")
                print(f"Role client thread -> last_probe_ntp_server_ip: |{self.last_probe_ntp_server_ip}|")
                result = subprocess.run( ['sudo', 'ntpdate', self.last_probe_ntp_server_ip], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode == 0:
                    print(f"AoIController: clock synced with {self.last_probe_ntp_server_ip}")
                    self.send_aoi_ACK(successed_command = "start", msm_id = msm_id)
                    while(not self.stop_thread_event.is_set()):
                        time.sleep(1 / packets_rate) # packets_rate can't be 0. The coordinator must check it.
                        timestamp_value = datetime.datetime.now().timestamp()
                        
                        timestamp_message = {
                            "timestamp" : timestamp_value,
                            "dummy_payload" : str("F" * payload_size) # Create a dummy payload of 'payload_size' bytes
                        }
                        print(f"AoI client: sending... -> {timestamp_value}" )
                        json_timestamp = json.dumps(timestamp_message)
                        self.measure_socket.sendto(json_timestamp.encode(), (self.last_probe_server_aoi, self.last_socket_port))
                else:
                    raise Exception(result.stderr.decode('utf-8'))
                    #print(f"AoIController: returncode -> {result.returncode}. STDOUT: {result.stdout.decode('utf-8')} , STDERR: {result.stderr.decode('utf-8')}")
                    #self.send_aoi_NACK(failed_command="start", error_info=)
            except Exception as e:
                stderr_command = str(e)
            finally:
                if stderr_command is not None:
                    self.send_aoi_NACK(failed_command="start", error_info=stderr_command, msm_id=msm_id)
        elif self.last_role == "Server":
            receive_error = None
            base_path = Path(__file__).parent
            aoi_measurement_folder_path = os.path.join(base_path, DEFAULT_AoI_MEASUREMENT_FOLDER)
            Path(aoi_measurement_folder_path).mkdir(parents=True, exist_ok=True)
            complete_file_path = os.path.join(aoi_measurement_folder_path, msm_id + ".csv")
            with open(complete_file_path, mode="w", newline="") as csv_file:
                try:
                    fieldnames = ["Timestamp", "AoI"]
                    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                    writer.writeheader()
                    print(f"Role server thread. PAYLOAD_SIZE-> {payload_size}")
                    #self.send_aoi_ACK(successed_command="start", msm_id=msm_id)
                    while(not self.stop_thread_event.is_set()):
                        data, addr = self.measure_socket.recvfrom(payload_size)
                        reception_timestamp = datetime.datetime.now().timestamp()

                        json_message = json.loads(data.decode())
                        client_timestamp = json_message["timestamp"]
                        dummy_payload = json_message["dummy_payload"]
                        
                        aoi = reception_timestamp - client_timestamp
                        writer.writerow({"Timestamp": reception_timestamp, "AoI": aoi})
                        print(f"Timestamp reception: |{reception_timestamp}| , Client timestamp: {client_timestamp} , AoI: |{aoi:.6f}| , DUMMY SIZE: |{len(dummy_payload)}| bytes")
                except socket.timeout:
                    receive_error = "SOCKET TIMEOUT. The client-probe is down?"
                    print(f"AoIController: {receive_error}")
                except Exception as e:
                    receive_error = str(e)
                finally:
                    if receive_error is not None:
                        self.send_aoi_NACK(failed_command="start", error_info=receive_error, msm_id=msm_id)
                        print(f"Exception in socket reception: {receive_error}")
                    csv_file.close()
            if receive_error is None:
                self.compress_and_publish_aoi_result(msm_id = msm_id)
            else:
                print("non inviato")
            shared_state.set_probe_as_ready()
        else:
            print(f"THREA START WITH STRANGE ROLE -> {self.last_role}")

    def stop_aoi_thread(self) -> str:
        if self.aoi_thread is None:
            return "No AoI measure in progress"
        self.stop_thread_event.set()
        self.aoi_thread.join()
        self.stop_thread_event.clear()
        self.measure_socket.close()
        return "OK"
    

    def stop_ntpsec_service(self):
        stop_command = ["sudo", "systemctl" , "stop" , "ntpsec" ] #[ "sudo systemctl stop ntpsec" ]
        result = subprocess.run(stop_command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        if result.returncode != 0:
            stdout_stop_command = result.stdout.decode('utf-8')
            stderr_stop_command = result.stderr.decode('utf-8')
            return f"Error in stopping ntsec service. Return code: {result.returncode}. STDOUT: |{stdout_stop_command}|. STDERR: |{stderr_stop_command}|"
        print("AoIController: ntpsec service disabled")
        return "OK"
    
    
    def start_ntpsec_service(self):
        start_command = [ "sudo", "systemctl" , "start" , "ntpsec" ]
        result = subprocess.run(start_command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        stdout_stop_command = result.stdout.decode('utf-8')
        time.sleep(0.5)
        if result.returncode != 0:
            stderr_stop_command = result.stderr.decode('utf-8')
            return f"Error in staring ntsec service. Return code: {result.returncode}. STDOUT: |{stdout_stop_command}|. STDERR: |{stderr_stop_command}|"
        print("AoIController: ntpsec service enabled")
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
        print("reset_vars()")
        self.last_measurement_id = None
        self.last_probe_ntp_server_ip = None
        self.last_socket_port = None
        self.last_role = None
        self.aoi_thread = None
        self.last_probe_server_aoi = None

    def compress_and_publish_aoi_result(self, msm_id):
        base_path = Path(__file__).parent
        aoi_measurement_file_path = os.path.join(base_path, DEFAULT_AoI_MEASUREMENT_FOLDER, msm_id + ".csv")
        df = pd.read_csv(aoi_measurement_file_path)

        # MEASURE AoI-TIMESERIES COMPRESSION
        aois = df.to_dict(orient='records')
        compressed_aois = cbor2.dumps(aois)
        c_aois_b64 = base64.b64encode(compressed_aois).decode("utf-8")
        aoi_min = df["AoI"].min()
        aoi_max = df["AoI"].max()

        # MEASURE RESULT MESSAGE
        json_energy_result = {
            "handler": "aoi",
            "type": "result",
            "payload": {
                "msm_id": msm_id,
                "c_aois_b64": c_aois_b64,
                "aoi_min" : aoi_min,
                "aoi_max" : aoi_max
             }
        }
        self.mqtt_client.publish_on_result_topic(result=json.dumps(json_energy_result))
        print(f"AoIController: compressed and published result of msm -> {msm_id}")