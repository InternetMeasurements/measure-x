import os
import json
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from src.modules.probesFirmware.mqttModule.mqttClient import ProbeMqttClient

class IperfController:
    def __init__(self, mqtt_client : ProbeMqttClient):

        self.config = None
        self.mqtt_client = mqtt_client
        self.last_role = None
        self.last_error = None
        
        # Iperf executed as Client - Parameters
        self.destination_server_ip = ""
        self.destination_server_port = 0
        self.tcp_protocol = False
        self.parallel_connections = 1
        self.output_json_filename = ""
        self.output_iperf_dir = ""
        self.reverse_function = False
        self.verbose_function = False
        self.total_repetition = 1

        # Iperf executed as Server - Parameters
        self.listening_port = None

        

    def read_configuration(self, role : str) -> bool :
        base_path = Path(__file__).parent
        config_path = os.path.join(base_path , 'configToBe' + role + '.yaml')
        if role == "Client":
            return self.read_client_configuration(config_path)
        elif role == "Server":
            return self.read_server_configuration(config_path)
        else:
            self.last_error = "Wrong role"
            return False

    def read_server_configuration(self, config_path):
        print(f"read_configuration_Server()")
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
            print(f"Configuration failed. Reason -> {e}")
            self.last_error = str(e)
            return False

    def read_client_configuration(self, config_path): # Reads the iperf yaml configuration file 
        print(f"read_configuration_Client()")
        try:
            with open(config_path, 'r') as file:
                self.config = yaml.safe_load(file)

            client_config = self.config['iperf_client']
            self.destination_server_ip = client_config['destination_server_ip']
            self.destination_server_port = int(client_config['destination_server_port'])
            self.tcp_protocol = True if (client_config['transport_protocol'] == "TCP") else False
            self.parallel_connections = int(client_config['parallel_connections'])
            self.output_json_filename = client_config['result_measurement_filename']
            self.output_iperf_dir = client_config['output_iperf_dir']
            self.reverse_function = client_config['reverse']
            self.verbose_function = client_config['verbose']
            self.total_repetition = int(client_config['total_repetition'])

            self.last_role = "Client"
            self.last_error = None
            return True
        except Exception as e:
            print(f"Configuration failed. Reason -> {e}")
            self.last_error = str(e)
            return False
    
    def get_usable_measurement_id(self, file_name):
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
    
    def run_iperf_execution(self, last_measurement_id):
        """This method execute the iperf3 program with the pre-loaded config."""
        message_info_execution = f"********* Execution Iperf3 to {self.destination_server_ip}, port: {self.destination_server_port}"
        base_path = Path(__file__).parent
        complete_output_json_dir = os.path.join(base_path, self.output_iperf_dir , self.output_json_filename + str(last_measurement_id) + ".json")

        command = "iperf3 "
        if self.last_role == "Client":
            command += "-c " + self.destination_server_ip + " -p " + str(self.destination_server_port)
            command += " -P " + str(self.parallel_connections)
            message_info_execution += " -P " + str(self.parallel_connections)
            if not self.tcp_protocol:
                command += " -u"
                message_info_execution += " [UDP]"
            if self.reverse_function:
                command += " -R"
                message_info_execution += " Reverse"
            if self.verbose_function:
                command += " -V"
                message_info_execution += " Verbose"
            command += " --json > " + complete_output_json_dir
            message_info_execution += " *********"
        else:
            command += "-s -p " + str(self.listening_port) # server mode and listening port
            if self.verbose_function:
                command += " -V"
        #print(command)
        exit_code = os.system(command)
        if self.last_role == "Client" :
            if exit_code != 0 :
                print(f"IPerf execution error: {exit_code}")
                return False
            print(f"Measurement saved in {complete_output_json_dir}")
        return True
    
    def run_iperf_repetitions(self) -> bool:
        if (self.config is None) or (self.last_role is None):
            print("iperfController: Can't start -> Not configured")
            return False
        
        repetition_count = 0

        last_measurement_ID = self.get_usable_measurement_id(self.output_json_filename)

        while repetition_count < self.total_repetition:
            print(f"\n*************** Repetition: {repetition_count + 1} ***************")
            if not self.run_iperf_execution(last_measurement_ID + repetition_count):
                break
            self.print_last_output_iperf(last_measurement_ID + repetition_count)
            repetition_count += 1
        return True
    
    
    def print_last_output_iperf(self, last_measurement_ID):
        """Stampa l'output dell'ultima esecuzione di Iperf salvata in un file JSON."""
        base_path = Path(__file__).parent
        completePathIPerfJson = os.path.join(base_path, self.output_iperf_dir, self.output_json_filename + str(last_measurement_ID) + ".json")
        if not os.path.exists(completePathIPerfJson):
            print("Last measurement not found!")
            return
        
        with open(completePathIPerfJson, 'r') as file:
            data = json.load(file)
        
        dt_object = datetime.strptime(data["start"]["timestamp"]["time"], "%a, %d %b %Y %H:%M:%S %Z")
        dt_object += timedelta(hours=2)
        formatted_time = dt_object.strftime("%d/%m/%y %H:%M:%S")

        source_ip = data["start"]["connected"][0]["local_host"]
        source_port = data["start"]["connected"][0]["local_port"]
        destination_ip = data["start"]["connected"][0]["remote_host"]
        destination_port = data["start"]["connected"][0]["remote_port"]
        bytes_received = data["end"]["sum_received"]["bytes"]
        duration = data["end"]["sum_received"]["seconds"]
        avg_speed = data["end"]["sum_received"]["bits_per_second"]
        print("\n****************** SUMMARY ******************")
        print(f"Timestamp: {formatted_time}")
        print(f"IP sorgente: {source_ip}, Porta sorgente: {source_port}")
        print(f"IP destinatario: {destination_ip}, Porta destinatario: {destination_port}")
        print(f"Velocità trasferimento {avg_speed} bits/s")
        print(f"Quantità di byte ricevuti: {bytes_received}")
        print(f"Durata misurazione: {duration} secondi\n")

    def iperf_command_handler(self, iperf_command : str):
        if iperf_command.startswith("role"):
            my_role = iperf_command.split('=')[1]
            if self.read_configuration(role = my_role) :
                self.mqtt_client.publish_command_ACK('iperf: conf') # ACK
            else:
                self.mqtt_client.publish_command_NACK('iperf: conf', self.last_error) # NACK
        elif iperf_command.startswith("start"):
            if self.last_role == "Server":
                self.run_iperf_execution(0) # the parameter is not used in Server mode
            else:
                if not self.run_iperf_repetitions():
                    self.mqtt_client.publish_command_NACK(iperf_command, "NO CONFIGURATION") # NACK
        else:
            print(f"iperfController: command not handled -> {iperf_command}")
            self.mqtt_client.publish_command_NACK(iperf_command, " Command not handled") # NACK
        self.last_error = None

