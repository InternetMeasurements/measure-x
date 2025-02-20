import json
import threading
import os
import subprocess
import platform
import signal
import psutil
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
        self.last_msm_id = None

        # Requests to commands_demultiplexer
        registration_response = registration_handler_request_function(
            interested_command = "ping",
            handler = self.ping_command_handler)
        if registration_response != "OK" :
            print(f"PingController: registration handler failed. Reason -> {registration_response}")
        
        
    def ping_command_handler(self, command : str, payload: json):
        msm_id = payload["msm_id"] if ("msm_id" in payload) else None
        if msm_id is None:
            self.send_ping_NACK(failed_command = command, error_info = "No measurement_id provided", measurement_related_conf = msm_id)
            return
        match command:
            case 'start':
                if not shared_state.set_probe_as_busy():
                    self.send_ping_NACK(failed_command = command, error_info = "PROBE BUSY", measurement_related_conf = msm_id)
                    return
                self.send_ping_ACK(successed_command = "start", measurement_related_conf = msm_id)
                self.ping_thread = threading.Thread(target=self.start_ping, args=(payload,))
                self.ping_thread.start()
            case 'stop':
                if (self.last_msm_id is not None) and (msm_id != self.last_msm_id):
                    self.send_ping_NACK(failed_command=command, 
                                        error_info="Measure_ID Mismatch: The provided measure_id does not correspond to the ongoing measurement",
                                        measurement_related_conf = msm_id)
                    return
                termination_message = self.stop_ping_thread()
                if termination_message != "OK":
                    self.send_ping_NACK(failed_command=command, error_info=termination_message, measurement_related_conf = msm_id)
                else:
                    self.send_ping_ACK(successed_command="stop", measurement_related_conf=msm_id)
                    self.last_msm_id = None
            case _:
                
                self.send_ping_NACK(failed_command = command, error_info = "Command not handled", measurement_related_conf = msm_id)
            

    def start_ping(self, payload : json):
        destination_ip = payload['destination_ip']
        packets_number = payload['packets_number']
        packets_size = payload['packets_size']
        msm_id = payload['msm_id']
        # Command construction
        if platform.system() == "Windows": # It's necessary for the output parsing to execute the ping-command-linux-based
            command = ["wsl", "ping"]
        else:
            command = ["ping"]
        command += [destination_ip, "-c", str(packets_number), "-s", str(packets_size)]
        timestamp = time.time() # start_timestamp
        try:
            self.last_msm_id = msm_id
            ping_result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            if ping_result.returncode == 0:
                parser = PingParsing()
                dict_result = parser.parse(ping_result.stdout)
                self.send_ping_result( json_ping_result=dict_result.as_dict(), 
                                    icmp_replies = dict_result.icmp_replies,
                                    timestamp = timestamp,
                                    msm_id=msm_id)
        except subprocess.CalledProcessError as e: 
            if e.returncode == -signal.SIGTERM: # if the returncode of the ping process is SIG_TERM, then the process has been stopped from the coordinator. So, it's better to "ACK it"
                self.send_ping_ACK(successed_command="stop", measurement_related_conf = msm_id)
            else: # if the return code is different from (SIG.TERM and CorrectTermination), then something strange happened, so the probe sends NACK to the coordinator
                self.send_ping_NACK(failed_command="start", error_info=str(e), measurement_related_conf = msm_id)
        except Exception as e: #In case of abnormal exception, send the nack to the coordinator
            self.send_ping_NACK(failed_command="start", error_info=str(e), measurement_related_conf=msm_id)
        finally:
            shared_state.set_probe_as_ready()
    
        
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
        

    def send_ping_ACK(self, successed_command, measurement_related_conf): # Incapsulating from the ping client
        json_ack = {
            "command": successed_command,
            "msm_id" : measurement_related_conf
            }
        self.mqtt_client.publish_command_ACK(handler='ping', payload = json_ack)
        print(f"PingController: sent ACK -> {successed_command} for measure -> |{measurement_related_conf}|")

    def send_ping_NACK(self, failed_command, error_info, measurement_related_conf = None):
        json_nack = {
            "command" : failed_command,
            "reason" : error_info,
            "msm_id" : measurement_related_conf
            }
        self.mqtt_client.publish_command_NACK(handler='ping', payload = json_nack)
        print(f"PingController: sent NACK, reason-> {error_info} for measure -> |{measurement_related_conf}|")

    def send_ping_result(self, json_ping_result : json, icmp_replies, timestamp, msm_id):
        my_ip = shared_state.get_probe_ip()
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