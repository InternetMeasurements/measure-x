import time
import os
import json
import subprocess
import base64, cbor2
from pathlib import Path
import threading
import signal
import psutil
from shared_resources import SharedState
from mqttModule.mqttClient import ProbeMqttClient

class IperfController:
    """
    Class that implements the THROUGHPUT measurement functionality using iperf3.
    Handles configuration, command dispatch, execution, and result reporting for both client and server roles.
    """
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function):
        """
        Initialize the IperfController with MQTT client and register the command handler.
        Sets up all configuration and state variables for both client and server roles.
        """

        self.shared_state = SharedState.get_instance()

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
        self.repetitions = 1
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
        """
        Reads the configuration from the payload and dispatches to the appropriate role handler.
        Returns 'OK' if configuration is successful, otherwise returns an error message.
        """
        if 'role' not in payload:
            return "Missing Role!"
        
        my_role = payload['role']
        if my_role == "Client": # If the role is client, then i ONLY check if the probe state is READY. This is beacuse, for the client, the Conf and Start are separated.
            if not self.shared_state.probe_is_ready():
                return "PROBE BUSY"
            return self.read_client_configuration(payload)
        elif my_role == "Server": # If the role is client, the i check if is possible to set its state ad BUSY. This is beacuse, for the server, the Conf and Start collide.
            if not self.shared_state.set_probe_as_busy():
                return "PROBE BUSY"
            return self.read_server_configuration(payload)
        else:
            return "Wrong Role!"

    def read_server_configuration(self, payload_conf : json) -> str:
        """
        Reads and sets the server configuration from the payload.
        Returns 'OK' if successful, otherwise returns an error message.
        """
        print(f"IperfController: read_configuration_Server()")
        try:
            self.listening_port = payload_conf['listen_port']
            self.verbose_function = payload_conf['verbose']
            self.last_measurement_id = payload_conf['msm_id']
            self.last_role = "Server"
            self.last_error = None
            return "OK"
        except Exception as e:
            print(f"IperfController: Configuration failed. Reason -> {e}")
            return str(e)

    def read_client_configuration(self, payload_conf : json) -> str:
        """
        Reads and sets the client configuration from the payload.
        Returns 'OK' if successful, otherwise returns an error message.
        """
        print(f"IperfController: read_configuration_Client()")
        try:
            self.destination_server_ip = payload_conf['destination_server_ip']
            self.destination_server_port = int(payload_conf['destination_server_port'])
            self.transport_protocol = payload_conf['transport_protocol']
            self.parallel_connections = int(payload_conf['parallel_connections'])
            self.output_json_filename = payload_conf['result_measurement_filename']
            self.reverse_function = payload_conf['reverse']
            self.verbose_function = payload_conf['verbose']
            self.repetitions = int(payload_conf['repetitions'])
            self.save_result_on_flash = payload_conf["save_result_on_flash"]
            self.last_measurement_id = payload_conf['msm_id']
            self.last_role = "Client"
            self.last_error = None
            return "OK"
        except Exception as e:
            print(f"IperfController: Configuration failed. Reason -> {e}")
            return str(e)


    def iperf_command_handler(self, command : str, payload: json):
        """
        Handles incoming iperf commands (conf, start, stop) and dispatches to the appropriate logic.
        Sends ACK/NACK responses as needed.
        """
        match command:
            case 'conf':
                measurement_related_conf = payload['msm_id']
                role_related_conf = payload['role']
                if not self.shared_state.probe_is_ready():
                    self.send_iperf_NACK(failed_command=command, error_info="PROBE BUSY", role = role_related_conf, msm_id = measurement_related_conf)
                    return
                
                configuration_message = self.read_configuration(payload)
                if configuration_message == "OK": # if the configuration goes good, then ACK, else NACK
                    self.send_iperf_ACK(successed_command = command, msm_id = measurement_related_conf)
                    if self.last_role == "Server":
                        self.start_iperf()
                else:
                    self.send_iperf_NACK(failed_command=command, error_info = configuration_message, role = role_related_conf, msm_id = measurement_related_conf)
            case 'start':
                if self.last_role == None:
                    self.send_iperf_NACK(failed_command=command, error_info="No configuration")
                    return
                if not self.shared_state.probe_is_ready():
                    self.send_iperf_NACK(failed_command = command, error_info = "PROBE BUSY", role = self.last_role)
                    return
                self.shared_state.set_probe_as_busy()
                if self.last_role == "Client":
                    if self.last_measurement_id is None:
                        self.send_iperf_NACK(failed_command="start", error_info="measure_id is None")
                        return
                    self.start_iperf()
                    self.last_execution_code = None
            case 'stop':
                msm_id = payload["msm_id"] if ("msm_id" in payload) else None
                if msm_id is None:
                    self.send_iperf_NACK(failed_command="stop", error_info="No measure_id provided", role="Server")
                    return
                termination_message = self.stop_iperf_thread(msm_id)
                if termination_message == "OK":
                    self.send_iperf_ACK(successed_command=command, msm_id=self.last_measurement_id)
                    self.shared_state.set_probe_as_ready()
                    self.reset_conf()
                else:
                    self.send_iperf_NACK(failed_command=command, error_info=termination_message, msm_id = msm_id)
            case _:
                print(f"IperfController: command not handled -> {command}")
                self.send_iperf_NACK(failed_command=command, error_info="Command not handled", msm_id=None)
    
        
    def start_iperf(self):
        """
        Starts the iperf measurement in a new thread, depending on the current role (client or server).
        """
        if self.last_role is None:
            self.shared_state.set_probe_as_ready()
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
        """
        Main loop for the iperf client thread. Handles repetitions, result publishing, and error handling.
        """
        repetition_count = 0
        execution_return_code = -2
        while (repetition_count < self.repetitions):
            time.sleep(0.5)
            print(f"\n*************** Repetition: {repetition_count + 1} ***************")
            execution_return_code = self.run_iperf_execution()
            if execution_return_code != 0: # 0 is the correct execution code
                break
            self.publish_last_output_iperf(repetition = repetition_count, last_result=((repetition_count + 1) == self.repetitions))
            repetition_count += 1
            time.sleep(0.5)

        if (execution_return_code != 0) and (execution_return_code != signal.SIGTERM):
            self.send_iperf_NACK(failed_command="start", error_info=self.last_error, msm_id=self.last_measurement_id)
        self.reset_conf()
        self.shared_state.set_probe_as_ready()
        

    
    def run_iperf_execution(self) -> int :  # BODY SERVER THREAD 
        """
        Executes the iperf3 program with the pre-loaded configuration.
        Handles both client and server roles. Returns the iperf process return code.
        """
        command = ["iperf3"]

        if self.last_role == "Client":
            command += ["-c", self.destination_server_ip]
            command += ["-p", str(self.destination_server_port)]
            command += ["-P", str(self.parallel_connections)]

            if self.transport_protocol != "TCP":
                command.append("-u")
                command.append("-b")
                command.append("1000M")
            else:
                command.append("--bandwidth")
                command.append("1000M")
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
                    if (self.last_json_result is not None) and ( 
                            ("error" in self.last_json_result) or ("Broken pipe" in self.last_json_result)
                            ) and (self.last_json_result["error"] == "the server has terminated"):
                        raise Exception("Connection refused from server")
                        
                    if self.save_result_on_flash: # if the save_on_flash mode in enabled...
                        base_path = Path(__file__).parent
                        complete_output_json_dir = os.path.join(base_path, self.output_iperf_dir , self.output_json_filename + self.last_measurement_id + ".json")
                        with open(complete_output_json_dir, "w") as output_file:
                            json.dump(self.last_json_result, output_file, indent=4)
                        print(f"IperfController: results saved in: {complete_output_json_dir}")
                except json.JSONDecodeError as e:
                    self.last_error = "Decode result json failed"
                    return -1
                except Exception as e:
                    if "Connection refused" in str(e):
                        self.last_error = str(e)
                    return -1                    
        else:
            print("IperfController: iperf3 server, listening...")
            command += ["-s", "-p", str(self.listening_port), "-i", "0"]
            if self.verbose_function:
                command.append("-V")
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if (result.returncode != 0) and (result.returncode != 1) and (result.returncode != signal.SIGTERM) :
                print(f"Iperf execution error. stderr: {result.stderr}  | return_code: {result.returncode }")
                self.send_iperf_NACK(failed_command="conf", error_info = result.stderr, role="Server", msm_id=self.last_measurement_id)
            self.shared_state.set_probe_as_ready()
        return result.returncode
    

    def stop_iperf_thread(self, msm_id):
        """
        Stops the iperf thread and kills the iperf3 process if running.
        Checks the measurement ID for safety. Returns 'OK' or an error message.
        """
        iperf_process_pid = None
        process_name = "iperf3"
        if (self.iperf_thread is not None) and (self.last_role is not None):
            for process in psutil.process_iter(['pid', 'name']):
                if process_name in process.info['name']:  # Finding the iperf3 process
                    iperf_process_pid = process.info['pid']
                    break
            if iperf_process_pid == None:
                return "Process " + process_name + "-" + self.last_role + " not in Execution"
            if msm_id != self.last_measurement_id:
                    return f"Measure_id mismatch: The provided measure_id does not correspond to the ongoing measurement {self.last_measurement_id}"
                    """
                    self.send_iperf_NACK(failed_command="stop", 
                                         error_info="",
                                         msm_id=msm_id, role="Server")
                    return
                    """
            try:
                os.kill(iperf_process_pid, signal.SIGTERM)
                self.iperf_thread.join()
                return "OK"
            except OSError as e:
                return str(e)
        else:
            return "Process " + process_name + " not in execution"


    def send_iperf_ACK(self, successed_command, msm_id = None):
        """
        Publishes an ACK message for a successful iperf command via MQTT.
        """
        json_ack = { 
            "command" : successed_command,
            "msm_id" : self.last_measurement_id if (msm_id is None) else msm_id
            }
        if (successed_command == "conf") and (self.last_role == "Server"):
            json_ack['port'] = self.listening_port
        print(f"IperfController: ACK sending -> {json_ack}")
        self.mqtt_client.publish_command_ACK(handler='iperf', payload=json_ack) 

    def send_iperf_NACK(self, failed_command, error_info, msm_id = None, role = None):
        """
        Publishes a NACK message for a failed iperf command via MQTT.
        """
        json_nack = {
            "command" : failed_command,
            "reason" : error_info,
            "role": self.last_role if (role is None) else role,
            "msm_id" : msm_id #self.last_measurement_id if (msm_id is None) else msm_id
            }
        print(f"IperfController: NACK sending -> {json_nack}")
        self.mqtt_client.publish_command_NACK(handler='iperf', payload = json_nack) 


    def publish_last_output_iperf(self, repetition : int , last_result : bool):
        """
        Publish the last measurement's output summary, loading it from memory and compressing the result.
        Publishes the result via MQTT.
        """
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

            compressed_full_result = cbor2.dumps(self.last_json_result)
            compressed_full_result_b64 = base64.b64encode(compressed_full_result).decode("utf-8")

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
                    "last_result": last_result,
                    "full_result_c_b64": compressed_full_result_b64
                }
            }

            # json_byte_result = json.dumps(json_copmpressed_data).encode('utf-8') Valutare se conviene binarizzarla

            self.mqtt_client.publish_on_result_topic(result=json.dumps(json_summary_data))
            self.last_json_result = None # reset the result about last iperf measurement
            print(f"IperfController: measurement [{self.last_measurement_id}] result published")
        except Exception as e:
            #print(f"Exception in publish_last_output_iperf -> {e} ")
            #print(f"last_json_result --> {self.last_json_result}")
            self.send_iperf_NACK(failed_command = "start", error_info = "May be the iperf-server is down",
                                   role = "Client", msm_id = self.last_measurement_id)
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
        """
        Resets all configuration and state variables for both client and server roles.
        """
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
        self.repetitions = 1
        self.save_result_on_flash = None
        self.last_json_result = None

        # Iperf Server - Parameters
        self.listening_port = None