"""
commands_multiplexer.py

This module defines the CommandsMultiplexer class, which acts as a central hub for managing communication and coordination between the coordinator and measurement probes in the Measure-X system. It handles registration and invocation of callbacks for results, status, and errors, manages probe IP/MAC information, and coordinates measurement preparation and stopping.
"""

import json
import time
import netifaces
import threading
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from modules.mongoModule.mongoDB import MongoDB, ErrorModel, STARTED_STATE, FAILED_STATE, COMPLETED_STATE
from modules.mqttModule.mqtt_client import Mqtt_Client

from concurrent.futures import ThreadPoolExecutor

class CommandsMultiplexer:
    """
    Central multiplexer for handling commands, results, status, and errors between the coordinator and probes.
    Manages callback registration, probe IP/MAC tracking, and measurement lifecycle operations.
    """
    def __init__(self, mongo_db : MongoDB):
        """
        Initialize the CommandsMultiplexer.
        Args:
            mongo_db (MongoDB): The MongoDB interface for measurement data.
        """
        self.mongo_db = mongo_db
        self.results_handler_callback = {}  # Maps result types to handler functions
        self.status_handler_callback = {}   # Maps status types to handler functions
        self.error_handler_callback = {}    # Maps error types to handler functions
        self.probes_preparer_callback = {}  # Maps measurement types to probe preparer functions
        self.measurement_stopper_callback = {}  # Maps measurement types to stopper functions
        self.mqtt_client = None
        self.probe_ip_lock = threading.Lock()  # Lock for thread-safe probe IP/MAC access
        self.probe_ip_mac = {}  # Maps probe_id to (ip, mac)
        self.probe_ip_for_clock_sync = {}  # Maps probe_id to clock sync IP
        self.event_ask_probe_ip = {}  # Maps probe_id to threading.Event for IP requests
        self.event_ask_probe_ip_for_clock_sync = {}  # Maps probe_id to threading.Event for clock sync IP requests
        self.coordinator_ip = self.get_coordinator_ip()  # Coordinator's IP address
        self.started_measurement = {}  # Maps measurement_id to measurement type

    def set_mqtt_client(self, mqtt_client : Mqtt_Client):
        """
        Set the MQTT client for publishing commands.
        Args:
            mqtt_client (Mqtt_Client): The MQTT client instance.
        """
        self.mqtt_client = mqtt_client

    def get_coordinator_ip(self):
        """
        Retrieve the coordinator's IP address from the default network interface.
        Returns:
            str: The coordinator's IP address, or '0.0.0.0' if not found.
        """
        try:
            gateways = netifaces.gateways()
            default_iface = gateways['default'][netifaces.AF_INET][1]
            my_ip = netifaces.ifaddresses(default_iface)[netifaces.AF_INET][0]['addr']
            print(f"CommandsMultiplexer: default nic -> |{default_iface}| , my_ip -> |{my_ip}| ")
        except KeyError as k:
            print(f"CommandsMultiplexer: exception in retrieve my ip -> {k} ")
            my_ip = "0.0.0.0"
        return my_ip

    def get_probe_ip_mac_if_present(self, probe_id):
        """
        Get the (IP, MAC) tuple for a probe if present.
        Args:
            probe_id (str): The probe identifier.
        Returns:
            tuple or (None, None): (IP, MAC) if present, else (None, None).
        """
        with self.probe_ip_lock:
            return self.probe_ip_mac[probe_id] if (probe_id in self.probe_ip_mac) else (None, None)
    
    def set_probe_ip_mac(self, probe_id, probe_ip, probe_mac):
        """
        Set the (IP, MAC) tuple for a probe.
        Args:
            probe_id (str): The probe identifier.
            probe_ip (str): The probe's IP address.
            probe_mac (str): The probe's MAC address.
        """
        with self.probe_ip_lock:
            self.probe_ip_mac[probe_id] = (probe_ip, probe_mac)

    def pop_probe_ip(self, probe_id):
        """
        Remove the (IP, MAC) entry for a probe.
        Args:
            probe_id (str): The probe identifier.
        """
        with self.probe_ip_lock:
            self.probe_ip_mac.pop(probe_id, None)

    def get_probe_ip_for_clock_sync_if_present(self, probe_id):
        """
        Get the clock sync IP for a probe if present.
        Args:
            probe_id (str): The probe identifier.
        Returns:
            str or None: The clock sync IP if present, else None.
        """
        with self.probe_ip_lock:
            return self.probe_ip_for_clock_sync[probe_id] if (probe_id in self.probe_ip_for_clock_sync) else None
    
    def set_probe_ip_for_clock_sync(self, probe_id, probe_ip_for_clock_sync):
        """
        Set the clock sync IP for a probe.
        Args:
            probe_id (str): The probe identifier.
            probe_ip_for_clock_sync (str): The clock sync IP address.
        """
        with self.probe_ip_lock:
            self.probe_ip_for_clock_sync[probe_id] = probe_ip_for_clock_sync
    
    def pop_probe_ip_for_clock_sync(self, probe_id):
        """
        Remove the clock sync IP entry for a probe.
        Args:
            probe_id (str): The probe identifier.
        """
        with self.probe_ip_lock:
            self.probe_ip_for_clock_sync.pop(probe_id, None)

    def ask_probe_ip_mac(self, probe_id, sync_clock_ip = None):
        """
        Request the (IP, MAC) or clock sync IP for a probe, waiting for a response if not already known.
        Args:
            probe_id (str): The probe identifier.
            sync_clock_ip (str, optional): If provided, requests clock sync IP instead of normal IP/MAC.
        Returns:
            tuple or str or None: (IP, MAC) or clock sync IP, or None if not received in time.
        """
        if sync_clock_ip is None:
            probe_ip, probe_mac = self.get_probe_ip_mac_if_present(probe_id = probe_id)
            if (probe_ip is not None) and (probe_mac is not None):
                return probe_ip, probe_mac
            self.event_ask_probe_ip[probe_id] = threading.Event()
            print(f"CommandsMultiplexer: Unknown probe |{probe_id}| IP - MAC. Asking...")
            self.root_service_send_command(probe_id, "get_probe_ip", {"coordinator_ip": self.coordinator_ip} )
            self.event_ask_probe_ip[probe_id].wait(timeout = 5)
            # ------------------------------- WAITING FOR PROBE IP RESPONSE -------------------------------
            self.event_ask_probe_ip.pop(probe_id, None)
            return self.get_probe_ip_mac_if_present(probe_id = probe_id)
        else:
            probe_ip_for_clock_sync = self.get_probe_ip_for_clock_sync_if_present(probe_id=probe_id)
            if probe_ip_for_clock_sync is not None:
                return probe_ip_for_clock_sync
            self.event_ask_probe_ip_for_clock_sync[probe_id] = threading.Event()
            print(f"CommandsMultiplexer: Unknown probe |{probe_id}| IP for Sync. Asking...")
            self.root_service_send_command(probe_id, "get_probe_ip", {"coordinator_ip": self.coordinator_ip} )
            self.event_ask_probe_ip_for_clock_sync[probe_id].wait(timeout = 5)
            # ------------------------------- WAITING FOR PROBE IP-FOR-CLOCK-SYNC RESPONSE -------------------------------
            self.event_ask_probe_ip_for_clock_sync.pop(probe_id, None)
        
    
    def add_result_callback(self, interested_result, handler):
        """
        Register a callback for a specific result type.
        Args:
            interested_result (str): The result type.
            handler (callable): The handler function.
        Returns:
            str: Status message.
        """
        if interested_result not in self.results_handler_callback:
            self.results_handler_callback[interested_result] = handler
            return "OK" #print(f"CommandsMultiplexer: Registered result handler for [{interested_result}]")
        else:
            return "There is already a registered handler for " + interested_result


    def add_status_callback(self, interested_status, handler):
        """
        Register a callback for a specific status type.
        Args:
            interested_status (str): The status type.
            handler (callable): The handler function.
        Returns:
            str: Status message.
        """
        if interested_status not in self.status_handler_callback:
            self.status_handler_callback[interested_status] = handler
            return "OK" #print(f"CommandsMultiplexer: Registered status handler for [{interested_status}]")
        else:
            return "There is already a registered handler for " + interested_status
        

    def add_error_callback(self, interested_error, handler):
        """
        Register a callback for a specific error type.
        Args:
            interested_error (str): The error type.
            handler (callable): The handler function.
        Returns:
            str: Status message.
        """
        if interested_error not in self.error_handler_callback:
            self.error_handler_callback[interested_error] = handler
            return "OK" #print(f"CommandsMultiplexer: Registered status handler for [{interested_status}]")
        else:
            return "There is already a registered handler for " + interested_error
        

    def add_probes_preparer_callback(self, interested_measurement_type, preparer_callback):
        """
        Register a callback to prepare probes for a specific measurement type.
        Args:
            interested_measurement_type (str): The measurement type.
            preparer_callback (callable): The preparer function (must return a triad).
        Returns:
            str: Status message.
        """
        # Be sure that all the "preparer methods" returns a string!
        if interested_measurement_type not in self.probes_preparer_callback:
            self.probes_preparer_callback[interested_measurement_type] = preparer_callback
            #print(f"CommandsMultiplexer: Registered probes preparer for [{interested_measurement_type}]")
            return "OK"
        else:
            return "There is already a probes-preparer for " + interested_measurement_type
    

    def add_measure_stopper_callback(self, interested_measurement_type, stopper_method_callback):
        """
        Register a callback to stop a measurement of a specific type.
        Args:
            interested_measurement_type (str): The measurement type.
            stopper_method_callback (callable): The stopper function.
        Returns:
            str: Status message.
        """
        if interested_measurement_type not in self.measurement_stopper_callback:
            self.measurement_stopper_callback[interested_measurement_type] = stopper_method_callback
            #print(f"CommandsMultiplexer: Registered measurement-stopper for [{interested_measurement_type}]")
            return "OK"
        else:
            return "There is already a measurement-stopper for " + interested_measurement_type
        

    def result_multiplexer(self, probe_sender: str, nested_result):  # invoked by MQTT module -> on_message on RESULT topic
        """
        Dispatch a result message to the appropriate registered handler.
        Args:
            probe_sender (str): The probe sending the result.
            nested_result (str): The JSON-encoded result message.
        """
        try:
            nested_json_result = json.loads(nested_result)
            handler = nested_json_result['handler']
            result = nested_json_result['payload']
            if handler in self.results_handler_callback:
                self.results_handler_callback[handler](probe_sender, result) # Multiplexing 
            else:
                print(f"CommandsMultiplexer: result_multiplexer: no registered handler for |{handler}|")
        except json.JSONDecodeError as e:
            print(f"CommandsMultiplexer: result_multiplexer: json exception -> {e}")
            

    def status_multiplexer(self, probe_sender, nested_status):  # invoked by MQTT module -> on_message on STATUS topic
        """
        Dispatch a status message to the appropriate registered handler.
        Args:
            probe_sender (str): The probe sending the status.
            nested_status (str): The JSON-encoded status message.
        """
        try:
            nested_json_status = json.loads(nested_status)
            handler = nested_json_status['handler']
            type = nested_json_status['type']  # This is the type of status message
            payload = nested_json_status['payload']
            if handler in self.status_handler_callback:
                self.status_handler_callback[handler](probe_sender, type, payload) # Multiplexing
            else:
                print(f"CommandsMultiplexer: status_multiplexer: no registered handler for |{handler}|. TYPE: {type}|\n-> PRINT: -> {payload}")
        except json.JSONDecodeError as e:
            print(f"CommandsMultiplexer: status_multiplexer: json exception -> {e}")


    def errors_multiplexer(self, probe_sender, nested_error):  # invoked by MQTT module -> on_message on ERROR topic
        """
        Dispatch an error message to the appropriate registered handler.
        Args:
            probe_sender (str): The probe sending the error.
            nested_error (str): The JSON-encoded error message.
        """
        try:
            nested_error_json = json.loads(nested_error)
            error_handler = nested_error_json['handler']
            error_command = nested_error_json['command']
            error_payload = nested_error_json['payload']
            if error_handler in self.error_handler_callback:
                self.error_handler_callback[error_handler](probe_sender, error_command, error_payload)
            else:
                print(f"CommandsMultiplexer: default error hanlder -> msg from |{probe_sender}| --> {nested_error}")
        except json.JSONDecodeError as e:
            print(f"CommandsMultiplexer: error_multiplexer: json exception -> {e}")
    

    def prepare_probes_to_measure(self, new_measurement : MeasurementModelMongo):  # invoked by REST module
        """
        Prepare probes for a new measurement by invoking the registered preparer callback.
        Args:
            new_measurement (MeasurementModelMongo): The measurement to prepare.
        Returns:
            tuple: (success_message, measurement_as_dict, error_cause)
        """
        measurement_type = new_measurement.type
        if measurement_type in self.probes_preparer_callback:
            # *** Ensure that all "preparer" methods return exactly three values (triad). ***
            success_message, measurement_as_dict, error_cause = self.probes_preparer_callback[measurement_type](new_measurement)
            
            # ******* WITH THESE LINE BELOW, IT'S POSSIBLE EXPLOIT THE COEX-MODULE IN PARALLEL WAY WITH THE 'measurement_type'-MODULE OF THE STARTED MEASURE  *******
            if success_message == "OK": # Naturally, only if the measure is started, it will be generated the coex traffic.
                if new_measurement.coexisting_application is not None:
                    coexisting_application_thread = threading.Thread(target=self.probes_preparer_callback['coex'], args=(new_measurement,))
                    coexisting_application_thread.start()
            # ******************************************************************************************************************************************** 

            if success_message == "OK":
                msm_id = measurement_as_dict["_id"]
                msm_type = measurement_as_dict["type"]
                self.started_measurement[msm_id] = msm_type
                print(f"CommandsMultiplexer: stored msm_id |{msm_id}| , type: |{msm_type}|")
            return success_message, measurement_as_dict, error_cause
        else:
            return "Error", "Check the measurement type", f"Unkown measure type: {measurement_type}"


    def measurement_stop_by_msm_id(self, msm_id_to_stop : str):  # invoked by REST module
        """
        Stop a measurement by its ID, invoking the appropriate stopper callback.
        Args:
            msm_id_to_stop (str): The measurement ID to stop.
        Returns:
            tuple: (result, message, error_cause)
        """
        measure_from_db = self.mongo_db.find_measurement_by_id(measurement_id=msm_id_to_stop)
        if isinstance(measure_from_db, ErrorModel):
            return "Error", measure_from_db.error_description, measure_from_db.error_cause
        
        if measure_from_db.state == STARTED_STATE:
            if measure_from_db.type in self.measurement_stopper_callback:
                stop_resul, stop_message, stop_error = self.measurement_stopper_callback[measure_from_db.type](msm_id_to_stop)
                
                if measure_from_db.coexisting_application is not None:
                    stop_coex_resul, stop_coex_message, stop_coex_error = self.measurement_stopper_callback['coex'](msm_id_to_stop)
                    if stop_coex_resul != "OK":
                        print(f"WARNING: unable to stop coex traffic, error -> {stop_coex_message}. Possible cause -> {stop_coex_error}")
                        stop_message += f" Warning: problem with stopping coex traffic -> {stop_coex_message}. Possible cause: {stop_coex_error}"
                
                return stop_resul, stop_message, stop_error
            return "Error", "Check the measurement type", f"Unkown measure type: {measure_from_db.type}"
        elif measure_from_db.state == FAILED_STATE:
            return "Error", "Measurement was failed", "Wrong id?"
        elif measure_from_db.state == COMPLETED_STATE:
            if measure_from_db.coexisting_application is not None:
                stop_coex_resul, stop_coex_message, stop_coex_error = self.measurement_stopper_callback['coex'](msm_id_to_stop)
                if stop_coex_resul == "OK":
                    return "OK", "Coex traffic stopped (The primary measurement was already completed).", None
                return stop_coex_resul, stop_coex_message, stop_coex_error
            return "Error", "Measurement already completed", "Wrong id?"
        else:
            return "Error", f"The measurement has an unknown state -> |{measure_from_db.state}|", "Unkown measure state"        
            

    # Default handler for the root_service probe message reception
    def root_service_default_handler(self, probe_sender, type, payload):
        """
        Default handler for root_service messages from probes. Updates probe IP/MAC and handles state changes.
        Args:
            probe_sender (str): The probe sending the message.
            type (str): The type of message (e.g., 'state').
            payload (dict): The message payload.
        """
        if type == "state":
            state_info = payload["state"] if ("state" in payload) else None
            if state_info is None:
                print(f"CommandsMultiplexer: root_service -> received state None from probe |{probe_sender}|")
                return
            probe_ip = payload["ip"] if ("ip" in payload) else None
            if (probe_ip is None) and (state_info != "OFFLINE"):
                print(f"CommandsMultiplexer: root_service -> received state -> |{state_info}| from probe |{probe_sender}| without ip")
                return
            probe_mac = payload["mac"] if ("mac" in payload) else None
            if (probe_mac is None) and (state_info != "OFFLINE"):
                print(f"CommandsMultiplexer: root_service -> received state -> |{state_info}| from probe |{probe_sender}| without mac")
                return
            probe_ip_for_clock_sync = payload["clock_sync_ip"] if ("clock_sync_ip" in payload) else None
            if (probe_ip_for_clock_sync is None) and (state_info != "OFFLINE"):
                print(f"CommandsMultiplexer: root_service -> received state -> |{state_info}| from probe |{probe_sender}| without ip for clock sync")
                return
            
            match state_info:
                case "ONLINE":
                    self.set_probe_ip_mac(probe_id = probe_sender, probe_ip = probe_ip, probe_mac=probe_mac)
                    self.set_probe_ip_for_clock_sync(probe_id = probe_sender, probe_ip_for_clock_sync = probe_ip_for_clock_sync)
                    if probe_ip in self.event_ask_probe_ip: # if this message is triggered by an "ask_probe_ip", then signal it (MAY BE THERE IS "SOMEONE" WAITING)
                        self.event_ask_probe_ip[probe_ip].set()
                    json_set_coordinator_ip = {"coordinator_ip": self.coordinator_ip}
                    self.root_service_send_command(probe_sender, "set_coordinator_ip", json_set_coordinator_ip)
                    print(f"CommandsMultiplexer: root_service -> |{probe_sender}| -> state [{payload['state']}] -> IP, MAC : |{self.get_probe_ip_mac_if_present(probe_sender)}|")
                case "UPDATE":
                    self.set_probe_ip_mac(probe_id = probe_sender, probe_ip = probe_ip, probe_mac=probe_mac)
                    self.set_probe_ip_for_clock_sync(probe_id = probe_sender, probe_ip_for_clock_sync = probe_ip_for_clock_sync)
                    if probe_ip in self.event_ask_probe_ip: # if this message is triggered by an "ask_probe_ip", then signal it (MAY BE THERE IS "SOMEONE" WAITING)
                        self.event_ask_probe_ip[probe_ip].set()
                case "OFFLINE":
                    self.pop_probe_ip(probe_id=probe_sender)
                    self.pop_probe_ip_for_clock_sync(probe_id = probe_sender)
                    print(f"CommandsMultiplexer: root_service -> probe [{probe_sender}] -> state [{state_info}]")
                case _:
                    print(f"CommandsMultiplexer: root_service -> received unknown state_info -> |{state_info}| , from probe -> |{probe_sender}|")


    def root_service_send_command(self, probe_id, command, root_service_payload):
        """
        Send a command to a probe via the MQTT client on the command topic.
        Args:
            probe_id (str): The probe to send the command to.
            command (str): The command name.
            root_service_payload (dict): The command payload.
        """
        json_command = {
            "handler": 'root_service',
            "command": command,
            "payload": root_service_payload
        }
        time.sleep(0.3)
        print(f"CommandsMultiplexer: root_service sending to |{probe_id}| , coordinator ip -> |{self.coordinator_ip}|")
        self.mqtt_client.publish_on_command_topic(probe_id = probe_id, complete_command=json.dumps(json_command))
