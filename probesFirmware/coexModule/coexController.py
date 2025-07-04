# coexController.py
# Controller for Coexisting Applications (COEX) functionality in Measure-X
# Handles configuration, traffic generation, and result/error reporting for COEX experiments

import os, signal
import json
from pathlib import Path
from mqttModule.mqttClient import ProbeMqttClient
from shared_resources import SharedState
from scapy.all import *

DEFAULT_THREAD_NAME = "coex_traffic_worker"
DEFAULT_PCAP_FOLDER = "pcap"

class CoexParamaters:
    """
    Data class for storing COEX measurement parameters.
    """
    def __init__(self, role = None, packets_size = None, packets_number = None, packets_rate = None,
                 socker_port = None, counterpart_probe_ip = None, counterpart_probe_mac = None, trace_name = None, duration = None):
        self.role = role
        self.packets_size = packets_size
        self.packets_number = packets_number # Client parameter
        self.packets_rate = packets_rate # Client parameter
        self.socker_port = socker_port
        self.counterpart_probe_ip = counterpart_probe_ip # Client parameter
        self.counterpart_probe_mac = counterpart_probe_mac
        self.trace_name = trace_name # Client parameter
        self.duration = duration

    def to_dict(self):
        """Return parameters as a dictionary."""
        return {
            "role": self.role,
            "packets_size" : self.packets_size,
            "packets_number": self.packets_number,
            "packets_rate": self.packets_rate,
            "socker_port": self.socker_port,
            "counterpart_probe_ip": self.counterpart_probe_ip,
            "counterpart_probe_mac" : self.counterpart_probe_mac,
            "trace_name" : self.trace_name,
            "duration" : self.duration
        }


class CoexController:
    """
    Main controller for COEX measurements. Handles configuration, start, stop, and result/error reporting.
    """
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function):
        # Initialize shared state and MQTT client
        self.shared_state = SharedState.get_instance()
        self.mqtt_client = mqtt_client
        self.last_msm_id = None
        self.last_coex_parameters = CoexParamaters()
        self.last_complete_trace_path = None
        self.stop_thread_event = threading.Event()
        self.thread_worker_on_socket = None
        #self.tcpliveplay_subprocess = None
        self.measure_socket = None
        self.future_stopper = None
        self.closed_by_manual_stop = threading.Event()
        self.closed_by_scheduled_stop = threading.Event()
        self.last_complete_trace_rewrited = None

        # Register handler for COEX commands
        registration_response = registration_handler_request_function(
            interested_command = "coex",
            handler = self.coex_command_handler)
        if registration_response != "OK" :
            print(f"CoexController: registration handler failed. Reason -> {registration_response}")
        
    def coex_command_handler(self, command : str, payload: json):
        """
        Handles incoming COEX commands (conf, start, stop) and dispatches to the appropriate logic.
        """
        msm_id = payload["msm_id"] if ("msm_id" in payload) else None
        if msm_id is None:
            self.send_coex_NACK(failed_command = command, error_info = "No measurement_id provided", measurement_related_conf = msm_id)
            return
        match command:
            case 'conf':
                if not self.shared_state.set_probe_as_busy():
                    self.send_coex_NACK(failed_command = command, error_info = "PROBE BUSY", measurement_related_conf = msm_id)
                    return
                check_parameters_msg = self.check_all_parameters(payload=payload)
                if check_parameters_msg != "OK":
                    self.send_coex_NACK(failed_command = command, error_info = check_parameters_msg, measurement_related_conf = msm_id)
                    self.shared_state.set_probe_as_ready()
                    return
                                
                thread_creation_msg = self.submit_thread_for_coex_traffic()
                if thread_creation_msg != "OK":
                    self.send_coex_NACK(failed_command = command, error_info = "PROBE BUSY", measurement_related_conf = msm_id)
                    self.shared_state.set_probe_as_ready()
                    return
                
                if self.last_coex_parameters.role == "Client": # THE SERVER WILL SEND conf ACK in body_worker_for_coex_traffic
                    self.send_coex_ACK(successed_command = "conf", measurement_related_conf = self.last_msm_id)
                self.print_coex_conf_info_message()       
                if self.last_coex_parameters.role == "Server": # ONLY the server starts the thread at CONF COMMAND
                    self.thread_worker_on_socket.start()
                

            case 'start':
                if self.shared_state.probe_is_ready():
                    self.send_coex_NACK(failed_command = command, error_info = "No coex measure in progress", measurement_related_conf = msm_id)
                    return
                if msm_id != self.last_msm_id:
                    self.send_coex_NACK(failed_command = command, 
                                        error_info = f"Measure_id mismatch: The provided measure_id does not correspond to the ongoing measurement |{self.last_msm_id}|", 
                                        measurement_related_conf = msm_id)
                    return
                
                if self.last_coex_parameters.role == "Client":
                    self.thread_worker_on_socket.start()

            case 'stop':
                if self.shared_state.probe_is_ready():
                    silent_mode = payload["silent"]
                    if not silent_mode:
                        self.send_coex_NACK(failed_command = command, error_info = "No coex measure in progress", measurement_related_conf = msm_id)
                    return
                
                if (self.last_msm_id is not None) and (msm_id != self.last_msm_id):
                    self.send_coex_NACK(failed_command=command, 
                                        error_info=f"Measure_ID Mismatch: The provided measure_id does not correspond to the ongoing measurement. Busy for |{self.last_msm_id}|",
                                        measurement_related_conf = msm_id)
                    return

                termination_message = self.stop_worker_socket_thread()
                if termination_message != "OK":
                    self.send_coex_NACK(failed_command=command, error_info=termination_message, measurement_related_conf = msm_id)
                #else:
                    #self.send_coex_ACK(successed_command="stop", measurement_related_conf = msm_id)
            case _:
                self.send_coex_NACK(failed_command = command, error_info = "Command not handled", measurement_related_conf = msm_id)


    def send_coex_ACK(self, successed_command, measurement_related_conf):
        """
        Publishes an ACK message for a successful COEX command via MQTT.
        """
        json_ack = {
            "command": successed_command,
            "msm_id" : measurement_related_conf
            }
        self.mqtt_client.publish_command_ACK(handler='coex', payload = json_ack)
        print(f"CoexController: sent ACK -> {successed_command} for measure -> |{measurement_related_conf}|")

    def send_coex_NACK(self, failed_command, error_info, measurement_related_conf = None):
        """
        Publishes a NACK message for a failed COEX command via MQTT.
        """
        json_nack = {
            "command" : failed_command,
            "reason" : error_info,
            "msm_id" : measurement_related_conf
            }
        self.mqtt_client.publish_command_NACK(handler='coex', payload = json_nack)
        print(f"CoexController: sent NACK for |{failed_command}| , reason-> {error_info} for measure -> |{measurement_related_conf}|")

    def send_coex_result(self, json_coex_result : json):
        """
        Publishes a result message for a COEX measurement via MQTT.
        """
        json_command_result = {
            "handler": "coex",
            "type": "result",
            "payload": json_coex_result
        }
        self.mqtt_client.publish_on_result_topic(result=json.dumps(json_command_result))
        print(f"CoexController: sent coex result -> {json_coex_result}")

    def send_coex_error(self, command_error, msm_id, reason):
        """
        Publishes an error message for a COEX measurement via MQTT.
        """
        json_error_payload = {
            "msm_id": msm_id,
            "reason": reason
        }

        json_command_error = {
            "handler": "coex",
            "command": command_error,
            "payload": json_error_payload
        }
        self.mqtt_client.publish_on_error_topic(error_msg=json.dumps(json_command_error))

    def submit_thread_for_coex_traffic(self):
        """
        Prepares and starts the thread that will handle COEX traffic (server or client).
        """
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
        """
        Main logic for COEX traffic generation and handling (server or client).
        Handles UDP traffic, pcap replay, and manages iptables rules for TCP RST suppression.
        """
        try:
            print(f"Thread_Coex: I'm the |{self.last_coex_parameters.role}| probe of measure |{self.last_msm_id}|")
            if self.last_coex_parameters.role == "Server":
                if self.last_coex_parameters.trace_name is None: # This means that there will be a Custom Traffic (UDP)
                    self.measure_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.measure_socket.bind((self.shared_state.get_probe_ip(), self.last_coex_parameters.socker_port))
                    self.send_coex_ACK(successed_command="conf", measurement_related_conf=self.last_msm_id)
                    print(f"Thread_Coex: Opened socket on IP: |{self.shared_state.get_probe_ip()}| , port: |{self.last_coex_parameters.socker_port}|")
                    print(f"Thread_Coex: Listening for {self.last_coex_parameters.packets_size} byte ...")
                    while(not self.stop_thread_event.is_set()):
                        data, addr = self.measure_socket.recvfrom(self.last_coex_parameters.packets_size)
                        print(f"Thread_Coex: Received data from |{addr}|. Data size: {len(data)} byte")
                    self.measure_socket.close()
                    self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id)
                    print("Thread_Coex: socket closed")
                else: # IF THE COEXITING TRAFFIC COMES FROM A PCAP...
                    cmd_to_add_rule_for_RST_packets_suppression = ["sudo", "iptables", "-A", "OUTPUT", "-p", "tcp", "--tcp-flags", "RST", 
                                                                    "RST", "-d", self.last_coex_parameters.counterpart_probe_ip, "--dport",
                                                                    str(self.last_coex_parameters.socker_port), "-j", "DROP"]
                    try:
                        result = subprocess.run(cmd_to_add_rule_for_RST_packets_suppression, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check = True)
                        if result.returncode == 0:
                            print(f"Thread_Coex: added rule for RST packets suppression for [{self.last_coex_parameters.counterpart_probe_ip}:{self.last_coex_parameters.socker_port}]")
                            self.send_coex_ACK(successed_command = "conf", measurement_related_conf = self.last_msm_id)
                        else:
                            print(f"Thread_Coex: error while adding suppression rule. Error -> : {result.stderr.decode()}")
                            self.send_coex_NACK(failed_command = "conf", error_info= f"Error while adding suppression rule. Error --> {result.stderr.decode()}", measurement_related_conf = self.last_msm_id)
                            self.shared_state.set_probe_as_ready()
                            self.reset_vars()
                            return
                        print(f"Thread_Coex: Waiting for coex traffic stop...")
                        socket_port = self.last_coex_parameters.socker_port
                        self.stop_thread_event.wait() # WARNING -> BLOCKING WAIT FOR Thread_Coex. Only the STOP command will wake-up it.
                        cmd_to_delete_rule_for_RST_packets_suppression = ["sudo", "iptables", "-D", "OUTPUT", "-p", "tcp", "--tcp-flags", "RST",
                                                                          "RST", "-d", self.last_coex_parameters.counterpart_probe_ip, "--dport",
                                                                          str(socket_port), "-j", "DROP"]
                        try:
                            result = subprocess.run(cmd_to_delete_rule_for_RST_packets_suppression, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            print(f"Thread_Coex: deleted rule for RST packets suppression for [{self.shared_state.get_probe_ip()}:{socket_port}]")
                            self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id) # Remember that in the stop_thread there a JOIN of this thread
                        except subprocess.CalledProcessError as e:
                            print(f"Thread_Coex: error while deleting suppression rule. Exception -> {e}")
                    except subprocess.CalledProcessError as e:
                        print(f"Thread_Coex: error while adding suppression rule. Exception -> {e}")
                        self.send_coex_NACK(failed_command = "conf", error_info= f"Error while adding suppression rule. Exception --> {e}", measurement_related_conf = self.last_msm_id)
                        self.shared_state.set_probe_as_ready()
                        self.reset_vars()
                    
            elif self.last_coex_parameters.role == "Client": # If i'm Coex Client
                # dst_hwaddr = src_hwaddr = "02:50:f4:00:00:01"
                src_mac = self.shared_state.get_probe_mac()
                dst_mac = self.last_coex_parameters.counterpart_probe_mac

                src_ip = self.shared_state.get_probe_ip()
                dst_ip = self.last_coex_parameters.counterpart_probe_ip
                dport = self.last_coex_parameters.socker_port

                if self.last_coex_parameters.trace_name is None:

                    rate = self.last_coex_parameters.packets_rate
                    n_pkts = self.last_coex_parameters.packets_number
                    size = self.last_coex_parameters.packets_size
                    pkt = Ether(src=src_mac, dst=dst_mac) / IP(src=src_ip, dst=dst_ip) / UDP(sport=30000, dport=dport) / Raw(RandString(size=size))
                    self.send_coex_ACK(successed_command="start", measurement_related_conf=self.last_msm_id)
                    if n_pkts == 0: # Then, the traffic will continue unitl "duration" seconds
                        if self.last_coex_parameters.duration != 0:
                            print(f"Thread_Coex: starting sendpfast. Future-kill scheduled to terminate after {self.last_coex_parameters.duration} seconds.")
                            self.future_stopper = threading.Timer(self.last_coex_parameters.duration, self.stop_worker_socket_thread, args=(True, self.last_msm_id,))
                            self.future_stopper.start()
                        d = sendpfast(pkt, mbps = rate, loop = 1, parse_results = True)

                    else:
                        if self.last_coex_parameters.duration != 0:
                            print(f"Thread_Coex: starting sendpfast. Future-kill scheduled to terminate after {self.last_coex_parameters.duration} seconds.")
                            self.future_stopper = threading.Timer(self.last_coex_parameters.duration, self.stop_worker_socket_thread, args=(True, self.last_msm_id,))
                            self.future_stopper.start()
                            d = sendpfast(pkt, mbps=rate, count=n_pkts, parse_results=True)
                            
                            if self.last_msm_id is not None:
                                self.future_stopper.cancel()
                                print("Thread_Coex: sendpfast has sent all packets. Deleted future-kill")
                                self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id)
                                self.shared_state.set_probe_as_ready()
                                self.reset_vars()
                        else:
                            d = sendpfast(pkt, mbps = rate, loop = 1, parse_results = True) # Send the packet forever (duration: 0)
                            print("Thread_Coex: sendpfast killed from stop")
 
                else: # Else, if a trace_name has been specified, then it will be used the combo tcprewrite + tcpreplay, bypassing scapy
                    tcprewrite_cmd = [  "sudo", "tcprewrite",
                                        "--infile=" +self.last_complete_trace_path, "--outfile="+ self.last_complete_trace_rewrited,
                                        "--srcipmap=0.0.0.0/0:" + src_ip , "--dstipmap=0.0.0.0/0:" + dst_ip,
                                        "--enet-smac=" + src_mac , "--enet-dmac=" + dst_mac ,
                                        "--portmap=" + str(dport) + ":" + str(dport)]
                    try:
                        result = subprocess.run(tcprewrite_cmd, check=True)
                        if result.returncode == 0: # If the tcprewrite is succesful...
                            print(f"Thread_Coex: tcprewrite OK")
                            if self.last_coex_parameters.duration != 0: # If the duration is 0, this means that the traffic generation will go forever (until you stop the primary measure)
                                print(f"Thread_Coex: tcpreplay future-kill scheduled to terminate after {self.last_coex_parameters.duration} seconds.")
                                self.future_stopper = threading.Timer(self.last_coex_parameters.duration, self.stop_worker_socket_thread, args=(True, self.last_msm_id,))
                                self.future_stopper.start()

                            print(f"Thread_Coex: tcpreplay started")
                            self.send_coex_ACK(successed_command = "start", measurement_related_conf = self.last_msm_id)
                            tcpreplay_cmd = ["sudo", "tcpreplay", "-i", self.shared_state.default_nic_name , self.last_complete_trace_rewrited]
                            result = subprocess.run(tcpreplay_cmd, check=True)
                            if result.returncode == 0:
                                deleted_future_stopper_msg = "."
                                if self.future_stopper:
                                    self.future_stopper.cancel()
                                    deleted_future_stopper_msg = ". Deleted scheduled-kill."
                                print(f"Thread_Coex: tcpreplay ended. All packets have been sent{deleted_future_stopper_msg}")
                                self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id)
                                self.shared_state.set_probe_as_ready()
                                self.reset_vars()
                            else:
                                print(f"TCPREPLAY TERMINATO CON {str(result.returncode)}")
                        else:
                            raise Exception(f"Thread_Coex: tcprewrite error -> {result.stderr.decode('utf-8')}")
                            #self.send_coex_NACK(successed_command="start", measurement_related_conf=self.last_msm_id, error_info=result.stderr.decode('utf-8'))    
                        
                    except Exception as e:
                        # ONLY in case of neither manully or scheduled stop, the NACK and others must me invoked.
                        if self.closed_by_manual_stop.is_set():
                            self.closed_by_manual_stop.clear()
                            #print(f"Thread_Coex: tcpreplay MANUALLY stopped.")
                            return
                            #self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id)
                        elif self.closed_by_scheduled_stop.is_set():
                            self.closed_by_scheduled_stop.clear()
                            return
                            #print(f"Thread_Coex: tcpreplay SCHEDULED stopped.")
                            #self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id)
                        else:
                            print(f"Thread_Coex: tcpreplay exception with error -> {e}")
                            self.send_coex_NACK(failed_command="start", measurement_related_conf=self.last_msm_id, error_info=str(e))
                            self.shared_state.set_probe_as_ready()
                            self.reset_vars()
                    """
                    packets = rdpcap(self.last_complete_trace_path)
                    for pkt in packets:
                        pkt[Ether].src = self.shared_state.get_probe_mac()
                        pkt[Ether].dst = self.last_coex_parameters.counterpart_probe_mac
                        pkt[Ether][IP].src = self.shared_state.get_probe_ip()
                        pkt[Ether][IP].dst = self.last_coex_parameters.counterpart_probe_ip

                        if TCP in pkt:
                            pkt[TCP].dport = self.last_coex_parameters.socker_port
                            pkt[TCP].sport = self.last_coex_parameters.socker_port
                            del pkt[TCP].chksum
                        elif UDP in pkt:
                            pkt[UDP].dport = self.last_coex_parameters.socker_port
                            pkt[UDP].sport = self.last_coex_parameters.socker_port
                            del pkt[UDP].chksum
                        del pkt[IP].chksum
                    """
                    """
                        PERFETTO, mi trovo con il grafico della misura 67e71df29bf739098c564855 AoI con Coex test.pcap.
                        Scapy rispetta il timing, quindi basterebbe catturare qualcosa di più pesante.
                    """
                    """
                    if self.last_coex_parameters.duration != 0: # If the duration is 0, this means that the traffic generation will go forever (until you stop the primary measure)
                        print(f"Thread_Coex: sendpfast future-kill scheduled to terminate after {self.last_coex_parameters.duration} seconds.")
                        future_stopper = threading.Timer(self.last_coex_parameters.duration, self.stop_worker_socket_thread, args=(True, self.last_msm_id,))
                        future_stopper.start()

                    print("Thread_Coex: staring sendpfast for trace-based coex traffic")
                    d = sendpfast(packets, realtime=True, file_cache=True, parse_results=True)

                    if (self.last_msm_id is not None) and (self.future_stopper is not None):
                        self.future_stopper.cancel()
                    print("Thread_Coex: sendpfast ended")
                    self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id)
                    self.shared_state.set_probe_as_ready()
                    self.reset_vars()
                    """
                    # BLOCKING
                    #self.tcpliveplay_subprocess.wait()
                #if self.last_msm_id is not None: # This is usefull because there will be a sort of Critical race between this thread and the stopper thread (future stopper)
                    #self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id)
        except Exception as e:
            print(f"CoexController: Role: {self.last_coex_parameters.role} , Exception -> |{str(e)}| , msm_id: |{self.last_msm_id}|")
            if (self.last_coex_parameters.role == "Server") and (not self.stop_thread_event.is_set()):
                self.send_coex_NACK(failed_command="conf", measurement_related_conf= self.last_msm_id, error_info = str(e))
                self.shared_state.set_probe_as_ready()
                self.reset_vars()
            

    def stop_worker_socket_thread(self, invoked_by_timer = False, measurement_coex_to_stop = ""):
        """
        Stops the COEX worker thread and cleans up resources. Handles both server and client roles.
        """
        print(f"stop_worker_socket_thread invoked_by_timer = {invoked_by_timer} , msm_id = {measurement_coex_to_stop}")
        try:
            if self.last_coex_parameters.role == "Server":
                self.stop_thread_event.set() # Setting the stop event for thread_worker_on_socket executed as Server 
                if self.last_coex_parameters.trace_name is None:
                    #print(f"Sending |{self.last_coex_parameters.packets_size}| byte to myself:{self.last_coex_parameters.socker_port}")
                    # Sending self.last_coex_parameters.packets_size BYTE to myself to wakeUp the thread blocked in recv. I won't use the SOCKET_TIMEOUT.
                    self.measure_socket.sendto( str("F" * self.last_coex_parameters.packets_size).encode() , (self.shared_state.get_probe_ip(), self.last_coex_parameters.socker_port))
                    self.thread_worker_on_socket.join()
                    self.measure_socket.close()
                else:
                    self.thread_worker_on_socket.join()
                self.shared_state.set_probe_as_ready()
                self.reset_vars()
            elif self.last_coex_parameters.role == "Client":
                if (invoked_by_timer): # If this is an automatic invocation, then we must be sure to stop the coex traffic.
                    if (measurement_coex_to_stop == self.last_msm_id): # May be this automatic invocation is delayed too much that fall in another measurement, so it's mandatory check the msm_id
                        self.closed_by_scheduled_stop.set()

                        proc = subprocess.run(["sudo", "pgrep", "tcpreplay"], capture_output=True, text=True)
                        if proc.stdout:
                            pid = int(proc.stdout.strip())
                            os.kill(pid, signal.SIGKILL)
                            print("CoexController: Scheduled-kill of tcpreplay.")
                        #self.send_coex_ACK(successed_command="stop", measurement_related_conf=measurement_coex_to_stop)
                        #self.reset_vars()
                        #self.shared_state.set_probe_as_ready()
                else:
                    deleted_future_stopper_msg = "."
                    if self.future_stopper:
                        self.future_stopper.cancel()
                        deleted_future_stopper_msg = ". Deleted scheduled-kill."
                    self.closed_by_manual_stop.set()
                    proc = subprocess.run(["sudo", "pgrep", "tcpreplay"], capture_output=True, text=True)
                    if proc.stdout:
                        pid = int(proc.stdout.strip())
                        os.kill(pid, signal.SIGKILL)
                        print(f"CoexController: Manual-kill of tcpreplay{deleted_future_stopper_msg}")
                self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id)
                self.shared_state.set_probe_as_ready()
                self.reset_vars()
            return "OK"
        except Exception as e:
            print(f"CoexController: Role -> {self.last_coex_parameters.role} , exception while closing socket -> {e}")
            return str(e)
        
    def print_coex_conf_info_message(self):
        """
        Prints configuration info for the current COEX measurement.
        """
        if self.last_coex_parameters.trace_name is None:
            print(f"CoexController: conf received -> CBR traffic |rate: {str(self.last_coex_parameters.packets_rate)}| , |size: {str(self.last_coex_parameters.packets_size)}|")
            print(f" , |number: {str(self.last_coex_parameters.packets_number)}| , |port: {str(self.last_coex_parameters.socker_port)}| , |counterpart_ip: {self.last_coex_parameters.counterpart_probe_ip}|"
                  f" , |counterpart_mac: {self.last_coex_parameters.counterpart_probe_mac}| , duration: |{str(self.last_coex_parameters.duration)}|s")
        else:
            print(f"CoexController: conf received -> trace traffic |trace_name: {self.last_coex_parameters.trace_name}| , |port: {str(self.last_coex_parameters.socker_port)}|"
                  f" , |counterpart_ip: {self.last_coex_parameters.counterpart_probe_ip}| , |counterpart_mac: {self.last_coex_parameters.counterpart_probe_mac}|"
                  f" , duration: |{str(self.last_coex_parameters.duration)}|s")

    def reset_vars(self):
        """
        Resets internal state variables after a measurement is finished or aborted.
        """
        print("CoexController: variables reset")
        self.last_msm_id = None
        self.last_coex_parameters = CoexParamaters()
        self.thread_worker_on_socket = None
        #self.tcpliveplay_subprocess = None
        self.last_complete_trace_path = None
        self.stop_thread_event.clear()
        if self.future_stopper is not None:
            self.future_stopper.cancel()
        self.future_stopper = None
        self.last_complete_trace_rewrited = None


    def check_all_parameters(self, payload : dict) -> str:
        """
        Checks all required parameters for a COEX measurement and sets them if valid.
        Returns 'OK' if all parameters are valid, otherwise returns an error message.
        """
        role = payload.get("role")
        counterpart_probe_ip = payload.get("counterpart_probe_ip")
        trace_name = payload.get("trace_name")
        packets_size = payload.get("packets_size")
        packets_rate = payload.get("packets_rate")
        packets_number = payload.get("packets_number")
        socket_port = payload.get("socket_port")
        counterpart_probe_mac = payload.get("counterpart_probe_mac")
        msm_id = payload.get("msm_id")
        duration = payload.get("duration")

        if role is None:
            return "No role provided"
        elif role == "Client":            
            if trace_name is not None: # Checking if pcap file exists
                trace_name_rewrited = trace_name.replace(".pcap", "_r.pcap") if (trace_name.endswith(".pcap")) else (trace_name + "_r.pcap")
                trace_name += ".pcap" if (not trace_name.endswith(".pcap")) else ""
                trace_directory = os.path.join(Path(__file__).parent, DEFAULT_PCAP_FOLDER)
                trace_path = os.path.join(trace_directory , trace_name)
                if not Path(trace_path).exists(): # If the pcap file is not present in the coex module path, the probe will check in its home dir
                    trace_directory = os.path.join("/", "home", os.getlogin(), DEFAULT_PCAP_FOLDER) # This change the "base path" of the rewrited trace path
                    trace_path = os.path.join("/", "home", os.getlogin(), DEFAULT_PCAP_FOLDER, trace_name)
                    if not Path(trace_path).exists():
                        return f"Trace file |{trace_name}| not found!"
                    print(f"CoexController: file {trace_name} found in alternative folder")
                else:
                    print(f"CoexController: file {trace_name} found in Coex Module folder")
                self.last_complete_trace_path = trace_path
                self.last_complete_trace_rewrited = os.path.join(trace_directory , trace_name_rewrited)
            else:          
                if packets_rate is None:
                    return "No packets rate provided"
                
                if packets_number is None:
                    return "No packets number provided"            
        
        if counterpart_probe_ip is None:
            return "No counterpart probe ip provided"

        if socket_port is None:
            return "No socket port provided"

        if counterpart_probe_mac is None:
            return "No counterpart probe mac provided"
            
        if msm_id is None:
            return "No measurement ID provided"
        
        self.last_msm_id = msm_id
        self.last_coex_parameters = CoexParamaters(role = role, packets_size = packets_size, packets_number = packets_number,
                                                   packets_rate = packets_rate, socker_port = socket_port, counterpart_probe_ip = counterpart_probe_ip,
                                                   counterpart_probe_mac = counterpart_probe_mac, trace_name = trace_name, duration=duration)
        return "OK"