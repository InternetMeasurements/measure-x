import json
import threading
import os
import subprocess
import platform
import signal
import psutil
import socket
import time
from pingparsing import PingParsing
from src.probesFirmware.mqttModule.mqttClient import ProbeMqttClient

""" Class that implements the latency, packets loss... funcionalities """
class PingController:
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function):
        self.mqtt_client = mqtt_client        
        self.ping_thread = None
        self.ping_result = None

        # Requests to commands_multiplexer
        registration_response = registration_handler_request_function(
            interested_command = "ping",
            handler = self.ping_command_handler)
        if registration_response != "OK" :
            print(f"PingController: registration handler failed. Reason -> {registration_response}")
        
        
    def ping_command_handler(self, command : str, payload: json):
        match command:
            case 'start':
                self.ping_thread = threading.Thread(target=self.start_ping, args=(payload,))
                self.ping_thread.start()
            case 'stop':
                termination_message = self.stop_ping_thread()
                if termination_message == "OK":
                    self.send_command_ack(successed_command=command)
                else:
                    self.send_command_nack(failed_command=command, error_info=termination_message)
                return
            case _:
                self.send_command_nack(failed_command = command, error_info = "Command not handled")
            

    def start_ping(self, payload : json):
        destination_ip = payload['destination_ip']
        packets_number = payload['packets_number']
        packets_size = payload['packets_size']
        measurement_id = payload['measurement_id']
        # Command construction
        if platform.system() == "Windows": # It's necessary for the output parsing, execute the ping command linux based
            command = ["wsl", "ping"]
        else:
            command = ["ping"]
        command += [destination_ip, "-c", str(packets_number), "-s", str(packets_size)]
        start_timestamp = time.time()
        ping_result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        if ping_result.returncode == 0:
            parser = PingParsing()
            dict_result = parser.parse(ping_result.stdout)
            self.send_ping_result( json_ping_result=dict_result.as_dict(), 
                                   icmp_replies = dict_result.icmp_replies,
                                   start_timestamp=start_timestamp,
                                   measurement_id=measurement_id)

            #parsed_str_result = json.dumps(dict_result.as_dict()) #self.parse_ping_result_in_str_json_result(ping_result=ping_result, destination_ip=destination_ip)
            #if parsed_str_result != "":
                #self.mqtt_client.publish_on_result_topic(result = parsed_str_result)
        elif ping_result.returncode != 15: # if the return code is different from (SIG.TERM and CorrectTermination), then send nack to coordinator
            self.send_command_nack(failed_command="ping", error_info=str(ping_result.returncode))
        else:
            self.send_command_ack(successed_command="stop")

    
        
    def stop_ping_thread(self):
        ping_process = None
        if self.ping_thread != None:
            for process in psutil.process_iter(['pid', 'name']):
                if 'ping' in process.info['name']:  # Finding the ping process
                    ping_process = process.info['pid']
                    break
        if ping_process == None:
            return "Process ping not in Execution"
        
        try:
            os.kill(ping_process, signal.SIGTERM)
            self.ping_thread.join()
            self.ping_thread = None
            return "OK"
        except OSError as e:
            return str(e)

    def send_command_ack(self, successed_command): # Incapsulating of the ping client
        json_ack = { "command": successed_command }
        print(f"PingController: ACK sending -> {json_ack}")
        self.mqtt_client.publish_command_ACK(handler='ping', payload = json_ack)

    def send_command_nack(self, failed_command, error_info):
        json_nack = {
            "command" : failed_command,
            "reason" : error_info
            }
        self.mqtt_client.publish_command_NACK(handler='ping', payload = json_nack)

    def parse_ping_result_in_str_json_result(self, ping_result, destination_ip) -> str:
        try:
            regex_patterns = {
                "host": r"PING (\S+) \(([\d\.]+)\)",  # Cattura l'host
                "packets_transmitted": r"(\d+) packets transmitted|(\d+) pacchetti inviati",
                "packets_received": r"(\d+) received|(\d+) ricevuti",
                "packet_loss": r"(\d+)% packet loss|(\d+)% perdita di pacchetti",
                "time": r"time (\d+ms)|tempo = (\d+ms)",
                "round_trip": r"rtt min/avg/max/mdev = ([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+) ms|min/avg/max/mdev = ([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+) ms",
                "ttl": r"ttl=(\d+)|ttl: (\d+)"
            }

            # Costruisci il dizionario JSON con i risultati
            ping_data = {
                "destination_ip": destination_ip,
                "resolved_host": None,
                "packets_transmitted": None,
                "packets_received": None,
                "packet_loss": None,
                "time": None,
                "round_trip": None,
                "ttl": None
            }

            for key, pattern in regex_patterns.items():
                match = re.search(pattern, ping_result.stdout)
                if match:
                    if key == "host":
                        ping_data["resolved_host"] = match.group(1)  # Cattura l'host risolto
                    elif key == "packets_transmitted":
                        ping_data["packets_transmitted"] = int(match.group(1) or match.group(2))
                    elif key == "packets_received":
                        ping_data["packets_received"] = int(match.group(1) or match.group(2))
                    elif key == "packet_loss":
                        ping_data["packet_loss"] = int(match.group(1) or match.group(2))
                    elif key == "time":
                        ping_data["time"] = match.group(1) or match.group(2)
                    elif key == "round_trip":
                        ping_data["round_trip"] = {
                            "min": float(match.group(1) or match.group(5)),
                            "avg": float(match.group(2) or match.group(6)),
                            "max": float(match.group(3) or match.group(7)),
                            "mdev": float(match.group(4) or match.group(8))
                        }
                    elif key == "ttl":
                        ping_data["ttl"] = int(match.group(1) or match.group(2))

            return json.dumps(ping_data, indent=4) # get back the ping result as json string! -> WARNING -> No need to dumps when publish it
        except subprocess.CalledProcessError as e:
            self.send_command_nack("result_parse", error_info=str(e))
            return ""
            