import os, signal
from pathlib import Path
import json
from mqttModule.mqttClient import ProbeMqttClient
from shared_resources import shared_state

from scapy.all import *

DEFAULT_THREAD_NAME = "coex_traffic_worker"

class CoexParamaters:
    def __init__(self, role = None, packets_size = None, packets_number = None, packets_rate = None, socker_port = None, server_probe_ip = None):
        self.role = role
        self.packets_size = packets_size
        self.packets_number = packets_number
        self.packets_rate = packets_rate
        self.socker_port = socker_port
        self.server_probe_ip = server_probe_ip


""" Class that implements the COEXISTING APPLICATIONS measurement funcionality """
class CoexController:
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function):
        self.mqtt_client = mqtt_client        
        self.last_msm_id = None
        self.last_coex_parameters = CoexParamaters()
        self.thread_worker_on_socket = None

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
            case 'conf':
                if not shared_state.set_probe_as_busy():
                    self.send_coex_NACK(failed_command = command, error_info = "PROBE BUSY", measurement_related_conf = msm_id)
                    return
                check_parameters_msg = self.check_all_parameters(payload=payload)
                if check_parameters_msg != "OK":
                    self.send_coex_NACK(failed_command = command, error_info = check_parameters_msg, measurement_related_conf = msm_id)
                    shared_state.set_probe_as_ready()
                    return
                
                thread_creation_msg = self.submit_thread_for_coex_traffic()
                if thread_creation_msg != "OK":
                    self.send_coex_NACK(failed_command = command, error_info = "PROBE BUSY", measurement_related_conf = msm_id)
                    shared_state.set_probe_as_ready()
                    return
                # Se va a buon fine la creazione del threas Server (per adesso), manda lui l'ACK
                self.thread_worker_on_socket.start()

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
                termination_message = self.stop_worker_socket_thread()
                if termination_message != "OK":
                    self.send_coex_NACK(failed_command=command, error_info=termination_message, measurement_related_conf = msm_id)
                else:
                    self.send_coex_ACK(successed_command="stop", measurement_related_conf=msm_id)
                    #self.last_msm_id = None
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


    def submit_thread_for_coex_traffic(self):
        try:
            self.thread_worker_on_socket = threading.Thread(target=self.body_worker_for_coex_traffic, name = DEFAULT_THREAD_NAME , args=())    
            return "OK"
        except socket.error as e:
            print(f"CoexController: Socket error -> {str(e)}")
            return f"Socket error: {str(e)}"
        except Exception as e:
            print(f"CoexController: Exception while creating socket -> {str(e)}")
            return str(e)


            
    def body_worker_for_coex_traffic(self):
        self.measure_socket = None
        try:
            if self.last_coex_parameters.role == "Server":
                self.measure_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.measure_socket.bind((shared_state.get_probe_ip(), self.last_coex_parameters.socker_port))
                #measure_socket.settimeout(socket_timeout)
                self.send_coex_ACK(successed_command = "conf", measurement_related_conf = self.last_msm_id)
                print(f"CoexController: Opened socket on IP: |{shared_state.get_probe_ip()}| , port: |{self.last_coex_parameters.socker_port}|")
                print(f"Listening for {self.last_coex_parameters.packets_size} byte, in while (true)")
                while(True):
                    self.measure_socket.recv(self.last_coex_parameters.packets_size)
            elif self.last_coex_parameters.role == "Client":                
                dst_hwaddr = src_hwaddr = "02:50:f4:00:00:01" 
                src_ip = shared_state.get_probe_ip()
                dst_ip = self.last_coex_parameters.server_probe_ip
                rate = self.last_coex_parameters.packets_rate
                n_pkts = self.last_coex_parameters.packets_number
                size = self.last_coex_parameters.packets_size
                dport = self.last_coex_parameters.socker_port

                pkt = Ether(src=src_hwaddr, dst=dst_hwaddr) / IP(src=src_ip, dst=dst_ip) / UDP(sport=30000, dport=dport) / Raw(RandString(size=size))

                d = sendpfast(pkt, mbps=rate, loop=n_pkts, parse_results=True)
                
        except socket.error as e:
                print(f"CoexController: Role: {self.last_coex_parameters.role} , Socket error -> {str(e)}")

    def stop_worker_socket_thread(self):
        try:
            if self.last_coex_parameters.role == "Server":
                self.measure_socket.close()
            elif self.last_coex_parameters.role == "Client":
                proc = subprocess.run(["pgrep", "-f", DEFAULT_THREAD_NAME], capture_output=True, text=True)
                if proc.stdout:
                    pid = int(proc.stdout.strip())
                    os.kill(pid, signal.SIGKILL)
                    print("UCCISO")
            return "OK"
        except Exception as e:
            print(f"CoexController: exception while closing socket -> {e}")
            return str(e)

    
            
    def scapy_test(self):
        # DEBUG METHOD -> NO MORE INVOKED
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


    def reset_vars(self):
        print("CoexgController: variables reset")
        self.last_msm_id = None
        self.last_udpping_params = CoexParamaters()
        self.thread_worker_on_socket = None

    def check_all_parameters(self, payload) -> str:        
        packets_size = payload["packets_size"] if ("packets_size" in payload) else None
        if packets_size is None:
            return "No packets size provided"
        
        packets_rate = payload["packets_rate"] if ("packets_rate" in payload) else None
        if packets_rate is None:
            return "No packets rate provided"
        
        packets_number = payload["packets_number"] if ("packets_number" in payload) else None
        if packets_number is None:
            return "No packets number provided"
        
        socket_port = payload["socket_port"] if ("socket_port" in payload) else None
        if socket_port is None:
            return "No socket port provided"
        
        server_probe_ip = None
        role = payload["role"] if ("role" in payload) else None
        if role is None:
            return "No role provided"
        elif role == "Client":
            server_probe_ip = payload["server_probe_ip"] if ("server_probe_ip" in payload) else None
            if server_probe_ip is None:
                return "No server probe ip provided"
            
        msm_id = payload["msm_id"] if ("msm_id" in payload) else None
        if msm_id is None:
            return "No measurement ID provided"
        
        self.last_msm_id = msm_id
        self.last_coex_parameters = CoexParamaters(role = role, packets_size = packets_size, packets_number = packets_number,
                                                   packets_rate = packets_rate, socker_port = socket_port, server_probe_ip=server_probe_ip)
        return "OK"