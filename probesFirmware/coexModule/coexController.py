import os, signal
import json
from pathlib import Path
from mqttModule.mqttClient import ProbeMqttClient
from shared_resources import SharedState

from scapy.all import *

DEFAULT_THREAD_NAME = "coex_traffic_worker"
DEFAULT_PCAP_FOLDER = "pcap"

class CoexParamaters:
    def __init__(self, role = None, packets_size = None, packets_number = None, packets_rate = None,
                 socker_port = None, counterpart_probe_ip = None, counterpart_probe_mac = None, trace_name = None, duration = None):
        self.role = role
        self.packets_size = packets_size
        self.packets_number = packets_number # Client paramter
        self.packets_rate = packets_rate # Client paramter
        self.socker_port = socker_port
        self.counterpart_probe_ip = counterpart_probe_ip # Client paramter
        self.counterpart_probe_mac = counterpart_probe_mac
        self.trace_name = trace_name # Client paramter
        self.duration = duration

    def to_dict(self):
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


""" Class that implements the COEXISTING APPLICATIONS measurement funcionality """
class CoexController:
    def __init__(self, mqtt_client : ProbeMqttClient, registration_handler_request_function):
        self.shared_state = SharedState.get_instance()
        self.mqtt_client = mqtt_client
        self.last_msm_id = None
        self.last_coex_parameters = CoexParamaters()
        self.last_complete_trace_path = None
        self.stop_thread_event = threading.Event()
        self.thread_worker_on_socket = None
        self.tcpliveplay_subprocess = None
        self.measure_socket = None


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
                    self.send_coex_ACK(successed_command = "start", measurement_related_conf = msm_id)


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
                else:
                    self.send_coex_ACK(successed_command="stop", measurement_related_conf = msm_id)
            case _:
                self.send_coex_NACK(failed_command = command, error_info = "Command not handled", measurement_related_conf = msm_id)


    def send_coex_ACK(self, successed_command, measurement_related_conf): # Incapsulating from the coex client
        json_ack = {
            "command": successed_command,
            "msm_id" : measurement_related_conf
            }
        self.mqtt_client.publish_command_ACK(handler='coex', payload = json_ack)
        print(f"CoexController: sent ACK -> {successed_command} for measure -> |{measurement_related_conf}|")

    def send_coex_NACK(self, failed_command, error_info, measurement_related_conf = None):
        json_nack = {
            "command" : failed_command,
            "reason" : error_info,
            "msm_id" : measurement_related_conf
            }
        self.mqtt_client.publish_command_NACK(handler='coex', payload = json_nack)
        print(f"CoexController: sent NACK for |{failed_command}| , reason-> {error_info} for measure -> |{measurement_related_conf}|")

    def send_coex_result(self, json_coex_result : json):
        json_command_result = {
            "handler": "coex",
            "type": "result",
            "payload": json_coex_result
        }
        self.mqtt_client.publish_on_result_topic(result=json.dumps(json_command_result))
        print(f"CoexController: sent coex result -> {json_coex_result}")

    def send_coex_error(self, command_error, msm_id, reason):
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
        try:
            print(f"Thread_Coex: I'm the |{self.last_coex_parameters.role}| probe of measure |{self.last_msm_id}|")
            if self.last_coex_parameters.role == "Server":
                if self.last_coex_parameters.trace_name is None: # This means that there will be a Custom Traffic (UDP)
                    self.measure_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.measure_socket.bind((self.shared_state.get_probe_ip(), self.last_coex_parameters.socker_port))
                    print(f"Thread_Coex: Opened socket on IP: |{self.shared_state.get_probe_ip()}| , port: |{self.last_coex_parameters.socker_port}|")
                    print(f"Thread_Coex: Listening for {self.last_coex_parameters.packets_size} byte ...")
                    while(not self.stop_thread_event.is_set()):
                        data, addr = self.measure_socket.recvfrom(self.last_coex_parameters.packets_size)
                        print(f"Thread_Coex: Received data from |{addr}|. Data size: {len(data)} byte")
                    self.measure_socket.close()
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
                        except subprocess.CalledProcessError as e:
                            print(f"Thread_Coex: error while deleting suppression rule. Exception -> {e}")
                    except subprocess.CalledProcessError as e:
                        print(f"Thread_Coex: error while adding suppression rule. Exception -> {e}")
                        self.send_coex_NACK(failed_command = "conf", error_info= f"Error while adding suppression rule. Exception --> {e}", measurement_related_conf = self.last_msm_id)
                        self.shared_state.set_probe_as_ready()
                        self.reset_vars()
                    
            elif self.last_coex_parameters.role == "Client":
                # dst_hwaddr = src_hwaddr = "02:50:f4:00:00:01"
                src_mac = self.shared_state.get_probe_mac()
                dest_mac = self.last_coex_parameters.counterpart_probe_mac

                src_ip = self.shared_state.get_probe_ip()
                dst_ip = self.last_coex_parameters.counterpart_probe_ip

                if self.last_coex_parameters.trace_name is None:

                    rate = self.last_coex_parameters.packets_rate
                    n_pkts = self.last_coex_parameters.packets_number
                    size = self.last_coex_parameters.packets_size
                    dport = self.last_coex_parameters.socker_port

                    pkt = Ether(src=src_mac, dst=dest_mac) / IP(src=src_ip, dst=dst_ip) / UDP(sport=30000, dport=dport) / Raw(RandString(size=size))

                    if self.last_coex_parameters.duration != 0:
                        future_stopper = threading.Timer(self.last_coex_parameters.duration, self.stop_worker_socket_thread, args=(True, self.last_msm_id,))
                        future_stopper.start()
                        d = sendpfast(pkt, mbps=rate, count=n_pkts, parse_results=True)
                        print("Sendpfast no loop terminata")
                        if self.last_msm_id is not None:
                            future_stopper.cancel()
                            self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id)
                            self.shared_state.set_probe_as_ready()
                            self.reset_vars()
                    else:
                        d = sendpfast(pkt, mbps = rate, loop = 1, parse_results = True) # Send the packet forever (duration: 0)
                        print("sendpfast con loop terminata")
                        #self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id)
                        #self.shared_state.set_probe_as_ready()
                        #self.reset_vars()
                else: # Else, if a trace_name has been specified, then it will be used tcpliveplay
                    # sudo tcpliveplay wlan0 tcp_out.pcap 192.168.143.211 2c:cf:67:6d:95:a3 60606
                    tcpliveplay_cmd = ['sudo', 'tcpliveplay', self.shared_state.default_nic_name, self.last_complete_trace_path, self.last_coex_parameters.counterpart_probe_ip,
                                       self.last_coex_parameters.counterpart_probe_mac, str(self.last_coex_parameters.socker_port) ]
                    self.tcpliveplay_subprocess = subprocess.Popen(tcpliveplay_cmd, stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL, text = True) # the tcpliveplay stdout is huge!
                    print(f"Thread_Coex: tcpliveplay coex traffic started")
                    
                    # If the duration is 0, this means that the traffic generation will go forever
                    if self.last_coex_parameters.duration != 0:
                        future_stopper = threading.Timer(self.last_coex_parameters.duration, self.stop_worker_socket_thread, args=(True, self.last_msm_id,))
                        future_stopper.start()

                    # BLOCKING
                    self.tcpliveplay_subprocess.wait()
                    print(f"Thread_Coex: tcpliveplay coex traffic finished")
                #if self.last_msm_id is not None: # This is usefull because there will be a sort of Critical race between this thread and the stopper thread (future stopper)
                    self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id)
                    
                
        except socket.error as e:
            print(f"CoexController: Role: {self.last_coex_parameters.role} , Socket error -> {str(e)}")
            if (self.last_coex_parameters.role == "Server") and (not self.stop_thread_event.is_set()):
                self.send_coex_error(command_error = "socket", msm_id = self.last_msm_id, reason = str(e))
                self.shared_state.set_probe_as_ready()
                self.reset_vars()
        
        self.shared_state.set_probe_as_ready()
        self.reset_vars()
            

    def stop_worker_socket_thread(self, invoked_by_timer = False, measurement_coex_to_stop = ""):
        try:
            if self.last_coex_parameters.role == "Server":
                self.stop_thread_event.set()
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
                """
                proc = subprocess.run(["pgrep", "-f", DEFAULT_THREAD_NAME], capture_output=True, text=True)
                if proc.stdout:
                    pid = int(proc.stdout.strip())
                    os.kill(pid, signal.SIGKILL)
                """
                if (invoked_by_timer): # If this is an automatic invocation, then we must be sure to stop the coex traffic.
                    print("Invoked by timer")
                    if (measurement_coex_to_stop == self.last_msm_id): # May be this automatic invocation is delayed too much that fall in another measurement, so it's mandatory check the msm_id
                        print("misure da fermare = quella del timer thread")
                        if self.tcpliveplay_subprocess is not None:
                            proc = subprocess.run(["sudo", "pgrep", "tcpliveplay"], capture_output=True, text=True)
                            if proc.stdout:
                                pid = int(proc.stdout.strip())
                                os.kill(pid, signal.SIGKILL)
                                print("UCCISIONE auto tcpliveplay OK")
                            #self.tcpliveplay_process.terminate()
                        else:
                            """
                            if self.thread_worker_on_socket is not None:
                                self.thread_worker_on_socket.terminate()
                                self.thread_worker_on_socket.join()
                                print("CoexController: automatic stop of Coex Application Traffic")
                            """
                            proc = subprocess.run(["sudo", "pgrep", "tcpreplay"], capture_output=True, text=True)
                            print(f"TENTATIVO UCCISIONE-AUTOMATICO-CBR --> |{proc.stdout}|")
                            if proc.stdout:
                                pid = int(proc.stdout.strip())
                                os.kill(pid, signal.SIGKILL)
                                print("UCCISIONE CBR OK")
                            
                            #Capire se queste 3 vanno bene qui per il CBR
                            self.send_coex_ACK(successed_command="stop", measurement_related_conf=measurement_coex_to_stop)
                            self.shared_state.set_probe_as_ready()
                            self.reset_vars()
                else:
                    if self.tcpliveplay_subprocess is not None:
                        proc = subprocess.run(["sudo", "pgrep", "tcpliveplay"], capture_output=True, text=True)
                        if proc.stdout:
                            pid = int(proc.stdout.strip())
                            os.kill(pid, signal.SIGKILL)
                            print("UCCISIONE manuale tcpliveplay OK")
                        #self.tcpliveplay_process.terminate()      
                    else:
                        """
                        if self.thread_worker_on_socket is not None:
                            self.thread_worker_on_socket.terminate()
                            self.thread_worker_on_socket.join()
                        """
                        print("CoexController: manual stop of Coex Application Traffic")
                        proc = subprocess.run(["sudo", "pgrep", "tcpreplay"], capture_output=True, text=True)
                        if proc.stdout:
                            pid = int(proc.stdout.strip())
                            os.kill(pid, signal.SIGKILL)
                            print("UCCISIONE CBR OK")
                        self.send_coex_ACK(successed_command="stop", measurement_related_conf=self.last_msm_id)
                        self.shared_state.set_probe_as_ready()
                        self.reset_vars()
                # Remember that, the future thread that will invoke this method, may be will have the resetted vars, so its role is None. 
            return "OK"
        except Exception as e:
            print(f"CoexController: Role -> {self.last_coex_parameters.role} , exception while closing socket -> {e}")
            return str(e)
        
    def print_coex_conf_info_message(self):
        if self.last_coex_parameters.trace_name is None:
            print(f"CoexController: conf received -> CBR traffic |rate: {str(self.last_coex_parameters.packets_rate)}| , |size: {str(self.last_coex_parameters.packets_size)}|")
            print(f" , |number: {str(self.last_coex_parameters.packets_number)}| , |port: {str(self.last_coex_parameters.socker_port)}| , |counterpart_ip: {self.last_coex_parameters.counterpart_probe_ip}|"
                  f" , |counterpart_mac: {self.last_coex_parameters.counterpart_probe_mac}| , duration: |{str(self.last_coex_parameters.duration)}|s")
        else:
            print(f"CoexController: conf received -> trace traffic |trace_name: {self.last_coex_parameters.trace_name}| , |port: {str(self.last_coex_parameters.socker_port)}|"
                  f" , |counterpart_ip: {self.last_coex_parameters.counterpart_probe_ip}| , |counterpart_mac: {self.last_coex_parameters.counterpart_probe_mac}|"
                  f" , duration: |{str(self.last_coex_parameters.duration)}|s")

    def reset_vars(self):
        print("CoexController: variables reset")
        self.last_msm_id = None
        self.last_coex_parameters = CoexParamaters()
        self.thread_worker_on_socket = None
        self.tcpliveplay_subprocess = None
        self.last_complete_trace_path = None
        self.stop_thread_event.clear()


    def check_all_parameters(self, payload : dict) -> str:
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
                trace_name += ".pcap" if (not trace_name.endswith(".pcap")) else ""
                trace_path = os.path.join(Path(__file__).parent, DEFAULT_PCAP_FOLDER, trace_name)
                print(f"First path: {trace_path}")
                if not Path(trace_path).exists(): # If the pcap file is not present in the coex module path, the probe will check in its home dir
                    trace_path = os.path.join("/", "home", os.getlogin(), DEFAULT_PCAP_FOLDER, trace_name)
                    print(f"Second path: {trace_path}")
                    
                    if not Path(trace_path).exists():
                        return f"Trace file |{trace_name}| not found!"
                self.last_complete_trace_path = trace_path
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