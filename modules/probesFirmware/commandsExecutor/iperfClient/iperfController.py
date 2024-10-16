import os
import json
import yaml
from pathlib import Path
from datetime import datetime, timedelta

class IperfController:
    def __init__(self):
        self.config = None
        self.destination_server_ip = ""
        self.destination_server_port = 0
        self.tcp_protocol = False
        self.parallel_connections = 1
        self.output_json_filename = ""
        self.output_iperf_dir = ""
        self.reverse_function = False
        self.verbose_function = False
        self.total_repetition = 1

        self.read_configuration()

    def read_configuration(self): # Reads the iperf yaml configuration file 
        try:
            base_path = Path(__file__).parent
            config_path = os.path.join(base_path , 'config.yaml')
            with open(config_path, 'r') as file:
                self.config = yaml.safe_load(file)

            config_list = self.config['iperf_client']
            self.destination_server_ip = config_list['destination_server_ip']
            self.destination_server_port = int(config_list['destination_server_port'])
            self.tcp_protocol = True if (config_list['transport_protocol'] == "TCP") else False
            self.parallel_connections = int(config_list['parallel_connections'])
            self.output_json_filename = config_list['result_measurement_filename']
            self.output_iperf_dir = config_list['output_iperf_dir']
            self.reverse_function = config_list['reverse']
            self.verbose_function = config_list['verbose']
            self.total_repetition = int(config_list['total_repetition'])

            return True
        except Exception as e:
            print(f"Configuration failed. Reason -> {e}")
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

        command = "iperf3 -c " + self.destination_server_ip + " -p " + str(self.destination_server_port)
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
        #print(command)
        
        exit_code = os.system(command)
        if exit_code != 0:
            print(f"IPerf execution error: {exit_code}")
            return False

        print(f"Measurement saved in {complete_output_json_dir}")
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

    def run_iperf_repetitions(self):
        repetition_count = 0

        last_measurement_ID = self.get_usable_measurement_id(self.output_json_filename)

        while repetition_count < self.total_repetition:
            print(f"\n*************** Repetition: {repetition_count + 1} ***************")
            if not self.run_iperf_execution(last_measurement_ID + repetition_count):
                break
            self.print_last_output_iperf(last_measurement_ID + repetition_count)
            repetition_count += 1
