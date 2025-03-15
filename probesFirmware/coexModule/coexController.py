import sys
import os
from pathlib import Path
import json
from mqttModule.mqttClient import ProbeMqttClient
from shared_resources import shared_state

from scapy.all import *

""" Class that implements the COEXISTING APPLICATIONS measurement funcionality """
class CoexController:
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function):
        self.mqtt_client = mqtt_client        
        self.last_msm_id = None

        # Requests to commands_demultiplexer
        registration_response = registration_handler_request_function(
            interested_command = "coex",
            handler = self.coex_command_handler)
        if registration_response != "OK" :
            print(f"CoexController: registration handler failed. Reason -> {registration_response}")
        
        
    def coex_command_handler(self, command : str, payload: json):
        msm_id = payload["msm_id"] if ("msm_id" in payload) else None
        if msm_id is None:
            self.send_coex_NACK(failed_command = command, error_info = "No measurement_id provided", measurement_related_conf = msm_id)
            return
        match command:
            case 'start':
                if not shared_state.set_probe_as_busy():
                    self.send_coex_NACK(failed_command = command, error_info = "PROBE BUSY", measurement_related_conf = msm_id)
                    return
                self.send_coex_ACK(successed_command = "start", measurement_related_conf = msm_id)

            case 'stop':
                if (self.last_msm_id is not None) and (msm_id != self.last_msm_id):
                    self.send_coex_NACK(failed_command=command, 
                                        error_info="Measure_ID Mismatch: The provided measure_id does not correspond to the ongoing measurement",
                                        measurement_related_conf = msm_id)
                    return
                termination_message = "DA IMPLEMENTARE"
                if termination_message != "OK":
                    self.send_coex_NACK(failed_command=command, error_info=termination_message, measurement_related_conf = msm_id)
                else:
                    self.send_coex_ACK(successed_command="stop", measurement_related_conf=msm_id)
                    self.last_msm_id = None
            case _:
                self.send_coex_NACK(failed_command = command, error_info = "Command not handled", measurement_related_conf = msm_id)
        

    def send_coex_ACK(self, successed_command, measurement_related_conf): # Incapsulating from the ping client
        json_ack = {
            "command": successed_command,
            "msm_id" : measurement_related_conf
            }
        self.mqtt_client.publish_command_ACK(handler='ping', payload = json_ack)
        print(f"CoexController: sent ACK -> {successed_command} for measure -> |{measurement_related_conf}|")

    def send_coex_NACK(self, failed_command, error_info, measurement_related_conf = None):
        json_nack = {
            "command" : failed_command,
            "reason" : error_info,
            "msm_id" : measurement_related_conf
            }
        self.mqtt_client.publish_command_NACK(handler='ping', payload = json_nack)
        print(f"CoexController: sent NACK, reason-> {error_info} for measure -> |{measurement_related_conf}|")

    def send_coex_result(self, json_coex_result : json):
        json_command_result = {
            "handler": "ping",
            "type": "result",
            "payload": json_coex_result
        }
        self.mqtt_client.publish_on_result_topic(result=json.dumps(json_command_result))
        print(f"CoexController: sent ping result -> {json_coex_result}")


    def scapy_test(self):
        from collections import Counter
        print("scapy test()")
        nuovo_ip_sorgente = shared_state.get_probe_ip()
        base_path = os.path.join(Path(__file__).parent)
        pcap_file_path = os.path.join(base_path, "pcap", "probe3_cella1_iliad.pcap")
        modified_packets = []

        packets = rdpcap(pcap_file_path)

        # Conta gli IP sorgenti nei pacchetti con flag SYN (probabili client)
        ip_sorgenti = [pkt[IP].src for pkt in packets if IP in pkt and TCP in pkt and pkt[TCP].flags & 2]
        ip_comune = Counter(ip_sorgenti).most_common(1)

        if not ip_comune:
            print(" Nessun IP sorgente identificato automaticamente!")
            return

        ip_originale = ip_comune[0][0]
        print(f"IP sorgente originale identificato: {ip_originale} , sostituito con {shared_state.get_probe_ip()}")

        for pkt in packets:
            if (IP in pkt) and (pkt[IP].src == ip_originale):
                pkt_mod = pkt.copy()
                pkt_mod[IP].src = nuovo_ip_sorgente
                del pkt_mod[IP].chksum
                if TCP in pkt_mod:
                    del pkt_mod[TCP].chksum
                modified_packets.append(pkt_mod)
            else:
                modified_packets.append(pkt)

        d = sendpfast(modified_packets, realtime=True, file_cache=True, parse_results=True)

        print(f"OUTPUT -> {d}")
