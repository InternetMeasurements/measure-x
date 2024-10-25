import os
import json
import subprocess
import socket
from pathlib import Path
import threading
import signal
import psutil
from src.probesFirmware.mqttModule.mqttClient import ProbeMqttClient

class IperfController:
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function):

        self.config = None
        self.mqtt_client = mqtt_client
        self.last_role = None
        self.last_error = None
        self.iperf_thread = None
        
        # Iperf Client - Parameters
        self.destination_server_ip = ""
        self.destination_server_port = 0
        self.tcp_protocol = False
        self.parallel_connections = 1
        self.output_json_filename = ""
        self.output_iperf_dir = ""
        self.reverse_function = False
        self.verbose_function = False # common parameter
        self.total_repetition = 1

        # Iperf Server - Parameters
        self.listening_port = None

        # Requests to commands_multiplexer
        registration_response = registration_handler_request_function(
            interested_command = "iperf",
            handler = self.iperf_command_handler)
        if registration_response != "OK" :
            print(f"IperfController: registration handler failed. Reason -> {registration_response}")
        
    def read_configuration(self, payload : json) -> bool :
        my_role = payload['role']
        if my_role == "Client":
            return self.read_client_configuration(payload)
        elif my_role == "Server":
            return self.read_server_configuration(payload)
        else:
            self.last_error = "Wrong Role!"
            return False

    def read_server_configuration(self, payload_conf : json):
        print(f"IperfController: read_configuration_Server()")
        try:
            self.listening_port = payload_conf['listen_port']
            self.verbose_function = payload_conf['verbose']
            self.last_role = "Server"
            self.last_error = None
            return True
        except Exception as e:
            print(f"IperfController: Configuration failed. Reason -> {e}")
            self.last_error = str(e)
            return False
        """
        try:
            with open(config_path, 'r') as file:
                self.config = yaml.safe_load(file)
                server_config = self.config['iperf_server']
                self.listening_port = server_config['listen_port']
                self.verbose_function = server_config['verbose']
                self.last_role = "Server"
                self.last_error = None
                return True
        except Exception as e:
            print(f"IperfController: Configuration failed. Reason -> {e}")
            self.last_error = str(e)
            return False
        """

    def read_client_configuration(self, payload_conf : json): # Reads the iperf yaml configuration file 
        print(f"IperfController: read_configuration_Client()")
        try:
            self.destination_server_ip = payload_conf['destination_server_ip']
            self.destination_server_port = int(payload_conf['destination_server_port'])
            self.tcp_protocol = True if (payload_conf['transport_protocol'] == "TCP") else False
            self.parallel_connections = int(payload_conf['parallel_connections'])
            self.output_json_filename = payload_conf['result_measurement_filename']
            self.reverse_function = payload_conf['reverse']
            self.verbose_function = payload_conf['verbose']
            self.total_repetition = int(payload_conf['total_repetition'])

            self.last_role = "Client"
            self.last_error = None
            return True
        except Exception as e:
            print(f"IperfController: Configuration failed. Reason -> {e}")
            self.last_error = str(e)
            return False

    def get_last_measurement_id(self, file_name):
        """It returns an id that can be used to the current measurement"""
        base_path = Path(__file__).parent
        output_path = os.path.join(base_path, self.output_iperf_dir)
        
        file_list = os.listdir(output_path)
        file_list = [measurement_file for measurement_file in file_list if measurement_file.startswith(file_name)]

        if not file_list:
            return 0
        
        sorted_list = sorted(file_list, key=lambda x: int(x.split('_')[1].split('.')[0]))
        last_element_ID = int(sorted_list[-1].split('_')[-1].split(".")[0])
        return last_element_ID + 1
    
    def run_iperf_execution(self, last_measurement_id) -> int :
        """This method execute the iperf3 program with the pre-loaded config."""
        base_path = Path(__file__).parent
        complete_output_json_dir = os.path.join(base_path, self.output_iperf_dir , self.output_json_filename + str(last_measurement_id) + ".json")
        command = ["iperf3"]

        if self.last_role == "Client":
            command += ["-c", self.destination_server_ip]
            command += ["-p", str(self.destination_server_port)]
            command += ["-P", str(self.parallel_connections)]

            if self.tcp_protocol != "TCP":
                command.append("-u")
            if self.reverse_function:
                command.append("-R")
            if self.verbose_function:
                command.append("-V")

            command.append("--json")
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)        
            
            if result.returncode != 0:
                print(f"IperfController: Errore nell'esecuzione di iperf: {result.stderr} | return_code: {result.returncode }")
            else:
                try: # Reading the result in the stdout
                    self.last_json_result = json.loads(result.stdout)
                    if self.save_result_on_flash: # if the save_on_flash mode in enabled...
                        base_path = Path(__file__).parent
                        complete_output_json_dir = os.path.join(base_path, self.output_iperf_dir , self.output_json_filename + str(last_measurement_id) + ".json")
                        with open(complete_output_json_dir, "w") as output_file:
                            json.dump(self.last_json_result, output_file, indent=4)
                        print(f"IperfController: results saved in: {complete_output_json_dir}")
                except json.JSONDecodeError:
                    print("IperfController: decode result json failed")
                    self.send_command_nack(failed_command="start", error_info="Decode result json failed")
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
            elif result.returncode != 15:
                print(f"Errore nell'esecuzione di iperf: {result.stderr} {result.stderr} | return_code: {result.returncode }")
                
        return result.returncode
    
    
    def start_iperf(self) -> int:
        if self.last_role is None:
            print("IperfController: Can't start -> Not configured")
            return -1
        
        execution_return_code = 0
        if self.last_role == "Server":
            self.iperf_thread = threading.Thread(target=self.run_iperf_execution, args=(0,))
            self.iperf_thread.start()
        else:
            repetition_count = 0
            last_measurement_ID = self.get_last_measurement_id(self.output_json_filename)
            execution_return_code = -2
            while repetition_count < self.total_repetition:
                print(f"\n*************** Repetition: {repetition_count + 1} ***************")
                execution_return_code = self.run_iperf_execution(last_measurement_ID + repetition_count)
                if execution_return_code != 0: # 0 is the correct execution code
                    break
                self.publish_last_output_iperf(last_measurement_ID + repetition_count)
                repetition_count += 1
        return execution_return_code

    def iperf_command_handler(self, command : str, payload: json):
        match command:
            case 'conf':
                if self.read_configuration(payload): # if the configuration goes good, then ACK, else NACK
                    self.send_command_ack(successed_command = command)
                    if self.last_role == "Server":
                        self.start_iperf()
                else:
                    self.send_config_nack(failed_command=command, error_info=self.last_error)
            case 'start':
                if self.last_role == "Client":
                    execution_code = self.run_iperf_repetitions()
                    if execution_code == -1:
                        self.send_config_nack(failed_command=command, error_info="No configuration")
                    else:
                        self.send_config_nack(failed_command=command, error_info=str(execution_code))
            case _:
                print(f"IperfController: command not handled -> {command}")
                self.mqtt_client.publish_command_NACK(handler='iperf', command=command, error_info="Command not handled") # NACK

    def send_config_ack(self, successed_command): # Incapsulating of the iperf-server-ip
        json_ack = { "command": successed_command }
        if self.last_role == "Server":
            hostname = socket.gethostname()
            my_ip = socket.gethostbyname(hostname)
            json_ack['ip'] = str(my_ip)
            json_ack['port'] = self.listening_port
        print(f"IperfController: ACK sent -> {json_ack}")
        self.mqtt_client.publish_command_ACK(handler='iperf', payload=json_ack) # volendo, posso anche passare command = command

    def send_config_nack(self, failed_command, error_info):
        json_nack = {
            "command" : failed_command,
            "reason" : error_info
            }
        self.mqtt_client.publish_command_NACK(handler='iperf', payload = json_nack) # NACK: No Configuration
   
    def publish_last_output_iperf(self, last_measurement_ID : int ):
        """ Publish the last measuremet's output summary loading it from flash """
        base_path = Path(__file__).parent
        completePathIPerfJson = os.path.join(base_path, self.output_iperf_dir, self.output_json_filename + str(last_measurement_ID) + ".json")
        if not os.path.exists(completePathIPerfJson):
            print("Last measurement not found!")
            return
        
        with open(completePathIPerfJson, 'r') as file:
            data = json.load(file)

        start_timestamp = data["start"]["timestamp"]["timesecs"]
        source_ip = data["start"]["connected"][0]["local_host"]
        source_port = data["start"]["connected"][0]["local_port"]
        destination_ip = data["start"]["connected"][0]["remote_host"]
        destination_port = data["start"]["connected"][0]["remote_port"]
        bytes_received = data["end"]["sum_received"]["bytes"]
        duration = data["end"]["sum_received"]["seconds"]
        avg_speed = data["end"]["sum_received"]["bits_per_second"]

        json_summary_data = {
            "handler": "iperf",
            "type": "result",
            "payload":
            {
                "measurement_id": last_measurement_ID,
                "start_timestamp": start_timestamp,
                "source_ip": source_ip,
                "source_port": source_port,
                "destination_ip": destination_ip,
                "destination_port": destination_port,
                "bytes_received": bytes_received,
                "duration": duration,
                "avg_speed": avg_speed
            }
        }

        # json_byte_result = json.dumps(json_copmpressed_data).encode('utf-8') Valutare se conviene binarizzarla

        self.mqtt_client.publish_result(json.dumps(json_summary_data))
        print(f"iperfController: measurement [{last_measurement_ID}] result published")

        """
        print("\n****************** SUMMARY ******************")
        print(f"Timestamp: {formatted_time}")
        print(f"IP sorgente: {source_ip}, Porta sorgente: {source_port}")
        print(f"IP destinatario: {destination_ip}, Porta destinatario: {destination_port}")
        print(f"Velocità trasferimento {avg_speed} bits/s")
        print(f"Quantità di byte ricevuti: {bytes_received}")
        print(f"Durata misurazione: {duration} secondi\n")
        """