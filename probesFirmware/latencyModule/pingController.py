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

    def send_ping_result(self, json_ping_result : json, icmp_replies, start_timestamp, measurement_id):
        hostname = socket.gethostname()
        my_ip = socket.gethostbyname(hostname)

        json_ping_result["source"] = my_ip
        json_ping_result["start_timestamp"] = start_timestamp
        json_ping_result["measurement_id"] = measurement_id
        json_ping_result["icmp_replies"] = icmp_replies

        json_command_result = {
            "handler": "ping",
            "type": "result",
            "payload": json_ping_result
        }

        self.mqtt_client.publish_on_result_topic(result=json.dumps(json_command_result))            