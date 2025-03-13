import os, csv
import time, datetime
import json
import subprocess, threading, signal
import socket
import base64, cbor2, pandas as pd
from pathlib import Path
from mqttModule.mqttClient import ProbeMqttClient
from shared_resources import shared_state

DEFAULT_UDPPing_MEASUREMENT_FOLDER = "udpping_measurements"

class UDPPingParameters:
    def __init__(self, role = None, probe_server_udpping = None, listen_port = None, packets_interval = None, live_mode = None, packets_number = None, packets_size = None):
        self.role = role
        self.probe_server_udpping = probe_server_udpping
        self.listen_port = listen_port
        self.packets_interval = packets_interval
        self.live_mode = live_mode
        self.packets_number = packets_number
        self.packets_size = packets_size

    def get_udpping_command_with_parameters(self):
        base_path = os.path.join(Path(__file__).parent) 
        command_to_execute = None
        if self.role == "Client":
            client_executable_path = os.path.join(base_path, 'udpClient')
            command_to_execute = [client_executable_path, '-a', self.probe_server_udpping, '-p', str(self.listen_port) ,
                                  '-s', str(self.packets_size), '-n', str(self.packets_number), '-i', str(self.packets_interval)]
            if self.live_mode:
                command_to_execute.append('-l')
        elif self.role == "Server":
            server_executable_path = os.path.join(base_path, 'udpServer')
            command_to_execute = [server_executable_path, '-p', str(self.listen_port)]
        return command_to_execute
    


class UDPPingController:
    """ Class that implements the UDP-PING measurement funcionality """
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function, wait_for_set_coordinator_ip):
        
        self.mqtt_client = mqtt_client
        self.last_measurement_id = None
        self.last_probe_ntp_server_ip = None
        
        self.udpping_thread = None
        self.stop_thread_event = threading.Event()

        self.last_udpping_params = UDPPingParameters()
        self.udpping_process = None

        self.wait_for_set_coordinator_ip = wait_for_set_coordinator_ip

        # Requests to commands_demultiplexer
        registration_response = registration_handler_request_function(
            interested_command = "udpping",
            handler = self.udpping_command_handler)
        if registration_response != "OK" :
            print(f"UDPPingController: registration handler failed. Reason -> {registration_response}")


    def udpping_command_handler(self, command : str, payload: json):
        msm_id = payload["msm_id"] if "msm_id" in payload else None
        if msm_id is None:
            self.send_udpping_NACK(failed_command=command, error_info="No measurement_id provided")
            return
        match command:
            case "disable_ntp_service":
                if not shared_state.set_probe_as_busy():
                    self.send_udpping_NACK(failed_command=command, error_info="PROBE BUSY", msm_id=msm_id)
                    return
                
                check_params_msg = self.check_all_parameters(payload)
                if check_params_msg != "OK":
                    self.send_udpping_NACK(failed_command=command, error_info = check_params_msg, msm_id=msm_id)
                    shared_state.set_probe_as_ready()
                    return

                disable_msg = self.stop_ntpsec_service()
                if disable_msg == "OK":
                    self.last_measurement_id = msm_id
                    self.send_udpping_ACK(successed_command = command, msm_id = msm_id)
                else:
                    self.send_udpping_NACK(failed_command = command, error_info = disable_msg, msm_id = msm_id)
                    shared_state.set_probe_as_ready()

            case "start":
                if (not shared_state.probe_is_ready()): # If the probe has an on-going measurement...
                    if self.last_measurement_id != msm_id: # If this ongoing measurement is not the one mentioned in the command
                        self.send_udpping_NACK(failed_command=command, 
                                            error_info="PROBE BUSY", # This error info can be also a MISMATCH error, but in this case is the same
                                            msm_id=msm_id)
                        return
                    
                    returned_msg = self.submit_thread_to_udpping_measure(msm_id = msm_id)
                    if returned_msg == "OK": # Thread submit and start are separated
                        self.udpping_thread.start()
                    else:
                        self.send_udpping_NACK(failed_command = command, error_info = returned_msg, msm_id = msm_id)
                else:
                    self.send_udpping_NACK(failed_command = command, error_info = "No UDP-PING measurement in progress", msm_id = msm_id)
            case "stop":
                if shared_state.probe_is_ready():
                    self.send_udpping_NACK(failed_command = command, error_info = "No UDP-PING measurement in progress", msm_id = msm_id)
                    return
                if self.last_measurement_id != msm_id:
                    self.send_udpping_NACK(failed_command=command, 
                                            error_info="Measure_id MISMATCH: The provided measure_id does not correspond to the ongoing measurement", 
                                            msm_id=msm_id)
                    return
                print("stopping...")
                termination_message = self.stop_udpping_thread()
                if termination_message == "OK":
                    self.send_udpping_ACK(successed_command=command, msm_id=msm_id)
                    if self.last_udpping_params.role == "Server":
                        self.reset_vars()
                else:
                    self.send_udpping_NACK(failed_command=command, error_info=termination_message)
                shared_state.set_probe_as_ready()
                
            
            case "enable_ntp_service":
                role = payload["role"] if ("role" in payload) else None
                if role is None:
                    self.send_udpping_NACK(failed_command=command, error_info="No role provided", msm_id=msm_id)
                    return
                if role == "Server":
                    if not shared_state.set_probe_as_busy():
                        self.send_udpping_NACK(failed_command=command, error_info="PROBE BUSY", msm_id=msm_id)
                        return
                    listen_port = payload["listen_port"] if ("listen_port" in payload) else None
                    if listen_port is None:
                        self.send_udpping_NACK(failed_command=command, error_info="No listen port provided", msm_id=msm_id)
                        shared_state.set_probe_as_ready()
                        return
                    
                    enable_msg = self.start_ntpsec_service()
                    if enable_msg == "OK":
                        self.last_udpping_params = UDPPingParameters(role=role, listen_port=listen_port)
                        self.last_measurement_id = msm_id
                        
                        returned_msg = self.submit_thread_to_udpping_measure(msm_id = msm_id)
                        if returned_msg == "OK":
                            self.udpping_thread.start()
                            #self.send_udpping_ACK(successed_command = command, msm_id = msm_id)
                        else:
                            self.send_udpping_NACK(failed_command = command, error_info = returned_msg, msm_id = msm_id)
                    else:
                        self.send_udpping_NACK(failed_command = command, error_info = enable_msg, msm_id = msm_id)
                        shared_state.set_probe_as_ready()
                elif role == "Client":
                    if self.last_measurement_id == msm_id:
                        enable_msg = self.start_ntpsec_service()
                        self.reset_vars()
                        if enable_msg == "OK":
                            self.send_udpping_ACK(successed_command = command, msm_id = msm_id)
                            #shared_state.set_probe_as_ready()
                        else:
                            self.send_udpping_NACK(failed_command = command, error_info = enable_msg, msm_id = msm_id)
                    elif self.last_measurement_id is None:
                        self.send_udpping_NACK(failed_command=command, error_info="No UDP-PING measurement in progress", msm_id = None)
                    else:
                        self.send_udpping_NACK(failed_command=command, 
                                            error_info="Measure_id MISMATCH: The provided measure_id does not correspond to the ongoing measurement", 
                                            msm_id=msm_id) 
                else:
                    self.send_udpping_NACK(failed_command = command, error_info = (f"Wrong role -> {role}"), msm_id = msm_id)
                
    """                NON SERVE PER UDPPING
    def create_socket(self, socket_timeout = None):
        try:
            self.measure_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.measure_socket.bind((shared_state.get_probe_ip(), self.last_listen_port))
            if self.last_role == "Server":
                if (socket_timeout is not None) and (socket_timeout > 0):
                    self.measure_socket.settimeout(socket_timeout)
                    print(f"UDPPingController: Opened socket on IP: |{shared_state.get_probe_ip()}| , port: |{self.last_listen_port}|")
                else:
                    print(f"UDPPingController: DEBUG -> Opened socket on IP: |{shared_state.get_probe_ip()}| , port: |{self.last_listen_port}|")
            #self.measure_socket.settimeout(10)
            return "OK"
        except socket.error as e:
            print(f"UDPPingController: Socket error while creating socket -> {str(e)}")
            return f"Socket error: {str(e)}"
        except Exception as e:
            print(f"UDPPingController: Exception while creating socket -> {str(e)}")
            self.measure_socket.close()
            return str(e)
    """


    def submit_thread_to_udpping_measure(self, msm_id):
        try:
            self.udpping_thread = threading.Thread(target=self.run_udpping, args=(msm_id,))
            return "OK"
        except Exception as e:
            returned_msg = (f"Exception while starting measure thread -> {str(e)}")
            print(f"UDPPingController: {returned_msg}")
            return returned_msg


    def run_udpping(self, msm_id):
        if self.last_udpping_params.role == "Client":
            stderr_command = None
            try:
                print(f"Role client thread -> last_probe_ntp_server_ip: |{self.last_probe_ntp_server_ip}|")
                result = subprocess.run( ['sudo', 'ntpdate', self.last_probe_ntp_server_ip], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode == 0:
                    print(f"UDPPingController: clock synced with {self.last_probe_ntp_server_ip}")
                    self.send_udpping_ACK(successed_command = "start", msm_id = msm_id)
                    base_path = Path(__file__).parent
                    udpping_measurement_folder_path = os.path.join(base_path, DEFAULT_UDPPing_MEASUREMENT_FOLDER)
                    Path(udpping_measurement_folder_path).mkdir(parents=True, exist_ok=True)
                    complete_file_path = os.path.join(udpping_measurement_folder_path, msm_id + ".csv")
                    with open(complete_file_path, "w") as output:
                        command = self.last_udpping_params.get_udpping_command_with_parameters()
                        self.udpping_process = subprocess.Popen(command, stdout=output, stderr=subprocess.PIPE, text=True)
                        print(f"UDPPingController: udpping tool started as Client")
                        self.udpping_process.wait()
                    
                    if (self.udpping_process is not None) and (self.udpping_process.returncode != 0) and (self.udpping_process.returncode != -15): # -15 is the SIGTERM signal
                        stderr_output = self.udpping_process.stderr.read()
                        errore_msg = f"UDPPingController: Process finished with error. STDERR: {stderr_output}"
                        print(errore_msg)
                        self.send_udpping_NACK(failed_command="enable_ntp_service", error_info=errore_msg, msm_id=msm_id)
                        return
                    print(f"UDPPingController: udpping tool stopped")
                    output.close()
                    time.sleep(1) # Waiting for closing file
                    self.compress_and_publish_udpping_result(msm_id=msm_id)
                else:
                    raise Exception(result.stderr.decode('utf-8'))                    
            except Exception as e:
                stderr_command = str(e)
                self.send_udpping_NACK(failed_command="start", error_info=stderr_command, msm_id=msm_id)
            shared_state.set_probe_as_ready()

        elif self.last_udpping_params.role == "Server":
            try:
                command = self.last_udpping_params.get_udpping_command_with_parameters()
                self.udpping_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                self.send_udpping_ACK(successed_command = "enable_ntp_service", msm_id = msm_id)
                print(f"UDPPingController: udpping tool started as Server")

                while(not self.stop_thread_event.is_set()): # "Busy" wait of thread otherwise the udpping tool will be closed
                    time.sleep(2)
                
                self.udpping_process.wait()
                print(f"UDPPingController: udpping tool stopped")
            except Exception as e:
                print(f"UDPPingController: exception during udpping execution -> {e}")
                self.send_udpping_NACK(failed_command="enable_ntp_service", error_info=str(e), msm_id=msm_id)
            finally:
                if (self.udpping_process is not None) and (self.udpping_process.returncode != 0) and (self.udpping_process.returncode != -15): # -15 is the SIGTERM signal
                    stderr_output = self.udpping_process.stderr.read()
                    stdout_output = self.udpping_process.stdout.read()
                    errore_msg = f"UDPPingController: Process finished with error. STDERR: |{stderr_output}| , STDOUT: |{stdout_output}|"
                    print(errore_msg)
                    self.send_udpping_NACK(failed_command="enable_ntp_service", error_info=errore_msg, msm_id=msm_id)
                
                self.udpping_process.stdout.close()
                shared_state.set_probe_as_ready()

    def stop_udpping_thread(self) -> str:
        if (self.udpping_thread is None) or (self.udpping_process is None):
            return "No udpping measure in progress"
        self.stop_thread_event.set()
        self.udpping_process.terminate()
        self.udpping_thread.join()
        self.udpping_process.wait()
        return "OK"
    

    def stop_ntpsec_service(self):
        stop_command = ["sudo", "systemctl" , "stop" , "ntpsec" ] #[ "sudo systemctl stop ntpsec" ]
        result = subprocess.run(stop_command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        if result.returncode != 0:
            stdout_stop_command = result.stdout.decode('utf-8')
            stderr_stop_command = result.stderr.decode('utf-8')
            self.reset_vars()
            return f"Error in stopping ntsec service. Return code: {result.returncode}. STDOUT: |{stdout_stop_command}|. STDERR: |{stderr_stop_command}|"
        print("UDPPingController: ntpsec service disabled")
        return "OK"
    
    
    def start_ntpsec_service(self):
        start_command = [ "sudo", "systemctl" , "start" , "ntpsec" ]
        result = subprocess.run(start_command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        stdout_stop_command = result.stdout.decode('utf-8')
        time.sleep(0.5)
        if result.returncode != 0:
            stderr_stop_command = result.stderr.decode('utf-8')
            return f"Error in staring ntsec service. Return code: {result.returncode}. STDOUT: |{stdout_stop_command}|. STDERR: |{stderr_stop_command}|"
        print("UDPPingController: ntpsec service enabled")
        return "OK"
    

    def send_udpping_ACK(self, successed_command, msm_id = None):
        json_ack = { 
            "command" : successed_command,
            "msm_id" : msm_id
            }
        print(f"UDPPingController: ACK sending -> {json_ack}")
        self.mqtt_client.publish_command_ACK(handler='udpping', payload=json_ack) 


    def send_udpping_NACK(self, failed_command, error_info, msm_id = None):
        json_nack = {
            "command" : failed_command,
            "reason" : error_info,
            "msm_id" : msm_id
            }
        print(f"UDPPingController: NACK sending -> {json_nack}")
        self.mqtt_client.publish_command_NACK(handler='udpping', payload = json_nack) 


    def compress_and_publish_udpping_result(self, msm_id):
        base_path = Path(__file__).parent
        udpping_measurement_file_path = os.path.join(base_path, DEFAULT_UDPPing_MEASUREMENT_FOLDER, msm_id + ".csv")
        
        columns_udpping_tool = ["SeqNr", "SendTime", "ServerTime", "ReceiveTime", "Client->Server", "Server->Client", "RTT (all times in ns)"]
        df = pd.read_csv(udpping_measurement_file_path, sep=';', skiprows=12, header=None, names=columns_udpping_tool) # Skipping the first 12 rows, redundant info.
        df = df.iloc[:-1] # Delete last file row, redundant info.
        data_lines = df.to_csv(index = False, sep=',', header = False) # Change the separator to the ',' intead of ';'
        new_header = ','.join(columns_udpping_tool)
        udpping_result = (f"{new_header}\n{data_lines}")

        compressed_udpping_output = cbor2.dumps(udpping_result)
        c_udpping_b64 = base64.b64encode(compressed_udpping_output).decode("utf-8")

        # MEASURE RESULT MESSAGE
        json_udpping_result = {
            "handler": "udpping",
            "type": "result",
            "payload": {
                "msm_id": msm_id,
                "c_udpping_b64": c_udpping_b64
             }
        }
        self.mqtt_client.publish_on_result_topic(result=json.dumps(json_udpping_result))

        print(f"UDPPingController: compressed and published result of msm -> {msm_id}")


    def reset_vars(self):
        print("UDPPingController: variables reset")
        self.last_measurement_id = None
        self.last_probe_ntp_server_ip = None
        self.last_listen_port = None
        self.stop_thread_event.clear()
        self.udpping_thread = None
        self.last_probe_server_udpping = None
        self.last_udpping_params = UDPPingParameters()
        self.udpping_process = None


    def check_all_parameters(self, payload) -> str:
        probe_ntp_server_ip = payload["probe_ntp_server"] if ("probe_ntp_server" in payload) else None
        if probe_ntp_server_ip is None:
            return "No probe-ntp-server provided"
        
        probe_server_udpping = payload["probe_server_udpping"] if ("probe_server_udpping" in payload) else None
        if probe_server_udpping is None:
            return "No server udpping provided"
        
        listen_port = payload["listen_port"] if ("listen_port" in payload) else None
        if listen_port is None:
            return "No listen port provided"
        
        packets_size = payload["packets_size"] if ("packets_size" in payload) else None
        if packets_size is None:
            return "No packets size provided"
        
        packets_number = payload["packets_number"] if ("packets_number" in payload) else None
        if packets_number is None:
            return "No packets number provided"
        
        packets_interval = payload["packets_interval"] if ("packets_interval" in payload) else None
        if packets_interval is None:
            return "No packets interval provided"
        
        live_mode = payload["live_mode"] if ("live_mode" in payload) else None
        if live_mode is None:
            return "No live mode provided"
        
        role = payload["role"] if ("role" in payload) else None
        if role is None:
            return "No role provided"        
        
        self.last_probe_ntp_server_ip = probe_ntp_server_ip
        self.last_udpping_params = UDPPingParameters(role=role, probe_server_udpping=probe_server_udpping, listen_port=listen_port, 
                                                     packets_interval=packets_interval, live_mode=live_mode,
                                                     packets_number=packets_number, packets_size=packets_size)
        return "OK"