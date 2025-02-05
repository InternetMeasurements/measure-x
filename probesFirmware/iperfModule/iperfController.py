import os
import json
import subprocess
from pathlib import Path
import threading
import signal
import psutil
from shared_resources import shared_state
from mqttModule.mqttClient import ProbeMqttClient

class IperfController:
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function):

        self.mqtt_client = mqtt_client
        self.last_role = None
        self.last_error = None
        self.iperf_thread = None
        self.last_measurement_id = None
        
        # Iperf Client - Parameters
        self.destination_server_ip = ""
        self.destination_server_port = None
        self.tcp_protocol = None
        self.parallel_connections = None
        self.output_json_filename = None
        self.output_iperf_dir = None
        self.reverse_function = None
        self.verbose_function = False # common parameter
        self.total_repetition = 1
        self.save_result_on_flash = None
        self.last_json_result = None

        # Iperf Server - Parameters
        self.listening_port = None

        # Requests to commands_demultiplexer
        registration_response = registration_handler_request_function(
            interested_command = "iperf",
            handler = self.iperf_command_handler)
        if registration_response != "OK" :
            print(f"IperfController: registration handler failed. Reason -> {registration_response}")


    def read_configuration(self, payload : json) -> str :
        if 'role' not in payload:
            return "Missing Role!"
        
        my_role = payload['role']
        if my_role == "Client": # If the role is client, then i ONLY check if the probe state is READY. This is beacuse, for the client, the Conf and Start are separated.
            if not shared_state.probe_is_ready():
                return "PROBE BUSY"
            return self.read_client_configuration(payload)
        elif my_role == "Server": # If the role is client, the i check if is possible to set its state ad BUSY. This is beacuse, for the server, the Conf and Start collide.
            if not shared_state.set_probe_as_busy():
                return "PROBE BUSY"
            return self.read_server_configuration(payload)
        else:
            return "Wrong Role!"

    def read_server_configuration(self, payload_conf : json) -> str:
        print(f"IperfController: read_configuration_Server()")
        try:
            self.listening_port = payload_conf['listen_port']
            self.verbose_function = payload_conf['verbose']
            self.last_measurement_id = payload_conf['measurement_id']
            self.last_role = "Server"
            self.last_error = None
            return "OK"
        except Exception as e:
            print(f"IperfController: Configuration failed. Reason -> {e}")
            return str(e)

    def read_client_configuration(self, payload_conf : json) -> str: # Reads the iperf yaml configuration file 
        print(f"IperfController: read_configuration_Client()")
        try:
            self.destination_server_ip = payload_conf['destination_server_ip']
            self.destination_server_port = int(payload_conf['destination_server_port'])
            self.transport_protocol = payload_conf['transport_protocol']
            self.parallel_connections = int(payload_conf['parallel_connections'])
            self.output_json_filename = payload_conf['result_measurement_filename']
            #self.measurement_id = payload_conf['measurement_id'] # REMEMBER --> You will read None during the configuration phase!
            self.reverse_function = payload_conf['reverse']
            self.verbose_function = payload_conf['verbose']
            self.total_repetition = int(payload_conf['total_repetition'])
            self.save_result_on_flash = payload_conf["save_result_on_flash"]
            self.last_measurement_id = payload_conf['measurement_id']
            self.last_role = "Client"
            self.last_error = None
            return "OK"
        except Exception as e:
            print(f"IperfController: Configuration failed. Reason -> {e}")
            return str(e)


    def iperf_command_handler(self, command : str, payload: json):
        match command:
            case 'conf':
                measurement_related_conf = payload['measurement_id']
                role_related_conf = payload['role']
                if not shared_state.probe_is_ready():
                    self.send_iperf_NACK(failed_command=command, error_info="PROBE BUSY", role_related_conf = role_related_conf, measurement_related_conf = measurement_related_conf)
                    return
                
                configuration_message = self.read_configuration(payload)
                if configuration_message == "OK": # if the configuration goes good, then ACK, else NACK
                    self.send_iperf_ACK(successed_command = command, measurement_related_conf = measurement_related_conf)
                    if self.last_role == "Server":
                        self.start_iperf()
                else:
                    self.send_iperf_NACK(failed_command=command, error_info = configuration_message, role_related_conf = role_related_conf, measurement_related_conf = measurement_related_conf)
            case 'start':
                if self.last_role == None:
                    self.send_iperf_NACK(failed_command=command, error_info="No configuration")
                    return
                if not shared_state.probe_is_ready():
                    self.send_iperf_NACK(failed_command = command, error_info = "Probe busy", role_related_conf = self.last_role)
                    return
                shared_state.set_probe_as_busy()
                if self.last_role == "Client":
                    #self.measurement_id = payload['measurement_id'] # Only in this moment the probe knows the measurment_id coming from Mongo
                    if self.last_measurement_id is None:
                        self.send_iperf_NACK(failed_command="start", error_info="measure_id is None")
                        return
                    self.start_iperf()
                    self.last_execution_code = None
            case 'stop':
                termination_message = self.stop_iperf_thread()
                if termination_message == "OK":
                    self.send_iperf_ACK(successed_command=command)
                    shared_state.set_probe_as_ready()
                    self.reset_conf()
                else:
                    self.send_iperf_NACK(failed_command=command, error_info=termination_message)
                self.last_measurement_id = None
                """
                if self.last_role == "Server" or self.last_role:
                    termination_message = self.stop_iperf_server_thread()
                    if termination_message == "OK":
                        self.send_iperf_ACK(successed_command=command)
                    else:
                        self.send_iperf_NACK(failed_command=command, error_info=termination_message)
                elif self.last_role == "Client":
                    termination_message = self.stop_iperf_server_thread()
                    if termination_message == "OK":
                        self.send_iperf_ACK(successed_command=command)
                    else:
                        self.send_iperf_NACK(failed_command=command, error_info=termination_message)
                """
            case _:
                print(f"IperfController: command not handled -> {command}")
                self.send_iperf_NACK(failed_command=command, error_info="Command not handled")
    
        
    def start_iperf(self):
        if self.last_role is None:
            shared_state.set_probe_as_ready()
            self.send_iperf_NACK(failed_command="start", error_info="No configuration")
            return
        
        if self.last_role == "Server":
            self.iperf_thread = threading.Thread(target=self.run_iperf_execution, args=())
            self.iperf_thread.start()
        elif self.last_role == "Client":
            self.iperf_thread = threading.Thread(target=self.iperf_client_body, args=())
            self.iperf_thread.start()
            #self.iperf_thread.join()


    def iperf_client_body(self): # BODY CLIENT THREAD 
        repetition_count = 0
        execution_return_code = -2
        while repetition_count < self.total_repetition:
            print(f"\n*************** Repetition: {repetition_count + 1} ***************")
            execution_return_code = self.run_iperf_execution()
            if execution_return_code != 0: # 0 is the correct execution code
                break
            self.publish_last_output_iperf(repetition = repetition_count, last_result=((repetition_count + 1) == self.total_repetition))
            repetition_count += 1

        if (execution_return_code != 0) and (execution_return_code != signal.SIGTERM):
            self.send_iperf_NACK(failed_command="start", error_info=self.last_error)
        else:
            self.reset_conf()
        shared_state.set_probe_as_ready()
        

    
    def run_iperf_execution(self) -> int :  # BODY SERVER THREAD 
        """This method execute the iperf3 program with the pre-loaded config. THIS METHOD IS EXECUTED BY A NEW THREAD, IF THE ROLE IS SERVER"""
        command = ["iperf3"]

        if self.last_role == "Client":
            command += ["-c", self.destination_server_ip]
            command += ["-p", str(self.destination_server_port)]
            command += ["-P", str(self.parallel_connections)]

            if self.transport_protocol != "TCP":
                command.append("-u")
            if self.reverse_function:
                command.append("-R")
            if self.verbose_function:
                command.append("-V")

            command.append("--json")
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)        
            
            if result.returncode != 0:
                if result.returncode != signal.SIGTERM:
                    self.last_error = result.stderr
                    print(f"IperfController: Iperf execution error: {self.last_error} | return_code: {result.returncode }")
            else:
                try: # Reading the result in the stdout
                    self.last_json_result = json.loads(result.stdout)
                    if self.save_result_on_flash: # if the save_on_flash mode in enabled...
                        base_path = Path(__file__).parent
                        complete_output_json_dir = os.path.join(base_path, self.output_iperf_dir , self.output_json_filename + self.last_measurement_id + ".json")
                        with open(complete_output_json_dir, "w") as output_file:
                            json.dump(self.last_json_result, output_file, indent=4)
                        print(f"IperfController: results saved in: {complete_output_json_dir}")
                except json.JSONDecodeError:
                    print("IperfController: decode result json failed")
                    self.send_iperf_NACK(failed_command="start", error_info="Decode result json failed", role_related_conf="Client", measurement_related_conf = self.last_measurement_id)
        else:
            #command += "-s -p " + str(self.listening_port) # server mode and listening port
            print("IperfController: iperf3 server, listening...")
            command += ["-s", "-p", str(self.listening_port)]
            if self.verbose_function:
                command.append("-V")
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                print(result.stdout)
            # elif result.returncode == 15: # This returncode 15, means that the subprocess has received a SIG.TERM signal, and then the process has been gently terminated
            elif result.returncode != signal.SIGTERM:
                print(f"Errore nell'esecuzione di iperf: {result.stderr}  | return_code: {result.returncode }")
                self.send_iperf_NACK(failed_command="conf", error_info=result.stderr, role_related_conf="Server", measurement_related_conf=self.last_measurement_id)
            shared_state.set_probe_as_ready()
        return result.returncode
    

    def stop_iperf_thread(self):
        iperf_process_pid = None
        process_name = "iperf3"
        if self.iperf_thread != None and self.last_role != None:
            for process in psutil.process_iter(['pid', 'name']):
                if process_name in process.info['name']:  # Finding the iperf3 process
                    iperf_process_pid = process.info['pid']
                    break
            if iperf_process_pid == None:
                return "Process " + process_name + "-" + self.last_role + " not in Execution"
            try:
                os.kill(iperf_process_pid, signal.SIGTERM)
                self.iperf_thread.join()
                return "OK"
            except OSError as e:
                return str(e)
        else:
            return "Process " + process_name + " not in execution"


    def send_iperf_ACK(self, successed_command, measurement_related_conf = None): # Incapsulating of the iperf-server-ip
        json_ack = { "command": successed_command }
        json_ack['measurement_id'] = self.last_measurement_id if (measurement_related_conf is None) else measurement_related_conf
        if (successed_command == "conf") and (self.last_role == "Server"):
            json_ack['port'] = self.listening_port
        print(f"IperfController: ACK sending -> {json_ack}")
        self.mqtt_client.publish_command_ACK(handler='iperf', payload=json_ack) 

    def send_iperf_NACK(self, failed_command, error_info, role_related_conf = None, measurement_related_conf = None):
        json_nack = {
            "command" : failed_command,
            "reason" : error_info,
            "role": self.last_role if (role_related_conf is None) else role_related_conf,
            "measurement_id" : self.last_measurement_id if (measurement_related_conf is None) else measurement_related_conf
            }
        self.mqtt_client.publish_command_NACK(handler='iperf', payload = json_nack) 


    def publish_last_output_iperf(self, repetition : int , last_result : bool):
        """ Publish the last measuremet's output summary loading it from flash """
        # base_path = Path(__file__).parent
        # completePathIPerfJson = os.path.join(base_path, self.output_iperf_dir, self.output_json_filename + str(self.last_measurement_id) + ".json")
        # if not os.path.exists(completePathIPerfJson):
        #    print("Last measurement not found!")
        #    return
        
        #with open(completePathIPerfJson, 'r') as file:
        #    data = json.load(file) # 'data' è diventato self.last_json_result

        try:
            start_timestamp = self.last_json_result["start"]["timestamp"]["timesecs"]
            source_ip = self.last_json_result["start"]["connected"][0]["local_host"]
            source_port = self.last_json_result["start"]["connected"][0]["local_port"]
            destination_ip = self.last_json_result["start"]["connected"][0]["remote_host"]
            destination_port = self.last_json_result["start"]["connected"][0]["remote_port"]
            bytes_received = self.last_json_result["end"]["sum_received"]["bytes"]
            duration = self.last_json_result["end"]["sum_received"]["seconds"]
            avg_speed = self.last_json_result["end"]["sum_received"]["bits_per_second"]

            json_summary_data = {
                "handler": "iperf",
                "type": "result",
                "payload":
                {
                    "msm_id": self.last_measurement_id,
                    "repetition_number": repetition,
                    "transport_protocol": self.transport_protocol,
                    "start_timestamp": start_timestamp,
                    "source_ip": source_ip,
                    "source_port": source_port,
                    "destination_ip": destination_ip,
                    "destination_port": destination_port,
                    "bytes_received": bytes_received,
                    "duration": duration,
                    "avg_speed": avg_speed,
                    "last_result": last_result
                }
            }

            # json_byte_result = json.dumps(json_copmpressed_data).encode('utf-8') Valutare se conviene binarizzarla

            self.mqtt_client.publish_on_result_topic(result=json.dumps(json_summary_data))
            self.last_json_result = None # reset the result about last iperf measurement
            print(f"iperfController: measurement [{self.last_measurement_id}] result published")
        except Exception as e:
            nack_message = "Check the probes IP"
            self.send_iperf_NACK(failed_command = "start", error_info = nack_message,
                                   role_related_conf = "Client", measurement_related_conf = self.last_measurement_id)
            self.reset_conf()

        """
        print("\n****************** SUMMARY ******************")
        print(f"Timestamp: {formatted_time}")
        print(f"IP sorgente: {source_ip}, Porta sorgente: {source_port}")
        print(f"IP destinatario: {destination_ip}, Porta destinatario: {destination_port}")
        print(f"Velocità trasferimento {avg_speed} bits/s")
        print(f"Quantità di byte ricevuti: {bytes_received}")
        print(f"Durata misurazione: {duration} secondi\n")
        """
    
    def reset_conf(self):
        self.last_role = None
        self.last_error = None
        self.iperf_thread = None
        self.last_measurement_id = None
        
        # Iperf Client - Parameters
        self.destination_server_ip = ""
        self.destination_server_port = 0
        self.transport_protocol = None
        self.parallel_connections = 1
        self.output_json_filename = None
        self.output_iperf_dir = None
        self.reverse_function = False
        self.verbose_function = False # common parameter
        self.total_repetition = 1
        self.save_result_on_flash = None
        self.last_json_result = None

        # Iperf Server - Parameters
        self.listening_port = None