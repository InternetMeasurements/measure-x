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
from mqttModule.mqttClient import ProbeMqttClient
from shared_resources import shared_state

""" Class that implements the LATENCY measurement funcionality """
class PingController:
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function):
        self.mqtt_client = mqtt_client        
        self.ping_thread = None
        self.ping_result = None

        # Requests to commands_demultiplexer
        registration_response = registration_handler_request_function(
            interested_command = "ping",
            handler = self.ping_command_handler)
        if registration_response != "OK" :
            print(f"PingController: registration handler failed. Reason -> {registration_response}")
        
        
    def ping_command_handler(self, command : str, payload: json):
        match command:
            case 'start':
                msm_id = payload['msm_id'] if ('msm_id' in payload) else None
                if not shared_state.set_probe_as_busy():
                    self.send_ping_NACK(failed_command = command, error_info = "PROBE BUSY", measurement_related_conf = msm_id)
                    return
                self.send_ping_ACK(successed_command = "start", measurement_related_conf = msm_id)
                self.ping_thread = threading.Thread(target=self.start_ping, args=(payload,))
                self.ping_thread.start()
            case 'stop':
                termination_message = self.stop_ping_thread()
                if termination_message != "OK":
                    self.send_ping_NACK(failed_command=command, error_info=termination_message)
            case _:
                self.send_ping_NACK(failed_command = command, error_info = "Command not handled")
            

    def start_ping(self, payload : json):
        destination_ip = payload['destination_ip']
        packets_number = payload['packets_number']
        packets_size = payload['packets_size']
        msm_id = payload['msm_id']
        # Command construction
        if platform.system() == "Windows": # It's necessary for the output parsing, execute the ping command linux based
            command = ["wsl", "ping"]
        else:
            command = ["ping"]
        command += [destination_ip, "-c", str(packets_number), "-s", str(packets_size)]
        timestamp = time.time() # start_timestamp
        try:
            ping_result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            if ping_result.returncode == 0:
                parser = PingParsing()
                dict_result = parser.parse(ping_result.stdout)
                self.send_ping_result( json_ping_result=dict_result.as_dict(), 
                                    icmp_replies = dict_result.icmp_replies,
                                    timestamp = timestamp,
                                    msm_id=msm_id)
            shared_state.set_probe_as_ready()
        except subprocess.CalledProcessError as e: 
            if e.returncode == -signal.SIGTERM: # if the returncode of the ping process is SIG_TERM, then the process has been stopped from the coordinator. So, it's better to "ACK it"
                self.send_ping_ACK(successed_command="stop")
            else: # if the return code is different from (SIG.TERM and CorrectTermination), then something strange happened, so the probe sends NACK to the coordinator
                self.send_ping_NACK(failed_command="ping", error_info=str(e))
        except Exception as e: #In case of abnormal exception, send the nack to the coordinator
            self.send_ping_NACK(failed_command="ping", error_info=str(e))

    
        
    def stop_ping_thread(self):
        ping_process = None
        process_name = "ping"
        if self.ping_thread != None:
            for process in psutil.process_iter(['pid', 'name']):  # Finding the ping process
                if process_name in process.info['name']: 
                    ping_process = process.info['pid']
                    break
        if ping_process == None:
            return "Process " + process_name + " not in Execution"
        
        try:
            os.kill(ping_process, signal.SIGTERM)
            self.ping_thread.join()
            self.ping_thread = None
            print(f"PingController: ping command stopped.")
            shared_state.set_probe_as_ready()
            return "OK"
        except OSError as e:
            shared_state.set_probe_as_ready()
            return str(e)
        

    def send_ping_ACK(self, successed_command, measurement_related_conf = None): # Incapsulating from the ping client
        json_ack = {
            "command": successed_command,
            "msm_id" : measurement_related_conf
            }
        self.mqtt_client.publish_command_ACK(handler='ping', payload = json_ack)
        print(f"PingController: sent ACK -> {successed_command}")

    def send_ping_NACK(self, failed_command, error_info, measurement_related_conf = None):
        json_nack = {
            "command" : failed_command,
            "reason" : error_info,
            "msm_id" : measurement_related_conf
            }
        self.mqtt_client.publish_command_NACK(handler='ping', payload = json_nack)
        print(f"PingController: sent NACK, reason-> {error_info}")

    def send_ping_result(self, json_ping_result : json, icmp_replies, timestamp, msm_id):
        hostname = socket.gethostname()
        my_ip = socket.gethostbyname(hostname)

        json_ping_result["source"] = my_ip
        json_ping_result["timestamp"] = timestamp
        json_ping_result["msm_id"] = msm_id

        essential_icmp_replies = []
        for icmp_reply in icmp_replies:
            essential_icmp_replies.append(
                {
                "bytes": icmp_reply["bytes"],
                "icmp_seq": icmp_reply["icmp_seq"],
                "ttl": icmp_reply["ttl"],
                "time": icmp_reply["time"]
                })

        json_ping_result["icmp_replies"] = essential_icmp_replies
        json_command_result = {
            "handler": "ping",
            "type": "result",
            "payload": json_ping_result
        }
        self.mqtt_client.publish_on_result_topic(result=json.dumps(json_command_result))
        print(f"PingController: sent ping result -> {json_ping_result}")