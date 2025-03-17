import json
import time
import netifaces
import threading
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from modules.mongoModule.mongoDB import MongoDB, ErrorModel, STARTED_STATE, FAILED_STATE, COMPLETED_STATE
from modules.mqttModule.mqtt_client import Mqtt_Client

class CommandsMultiplexer:
    def __init__(self, mongo_db : MongoDB):
        self.mongo_db = mongo_db
        self.results_handler_callback = {}
        self.status_handler_callback = {}
        self.error_handler_callback = {}
        self.probes_preparer_callback = {}
        self.measurement_stopper_callback = {}
        self.mqtt_client = None
        self.probe_ip_lock = threading.Lock()
        self.probe_ip = {}
        self.probe_ip_for_clock_sync = {}
        self.event_ask_probe_ip = {}
        self.event_ask_probe_ip_for_clock_sync = {}
        self.coordinator_ip = self.get_coordinator_ip()
        self.started_measurement = {}

    def set_mqtt_client(self, mqtt_client : Mqtt_Client):
        self.mqtt_client = mqtt_client

    def get_coordinator_ip(self):
        try:
            gateways = netifaces.gateways()
            default_iface = gateways['default'][netifaces.AF_INET][1]
            my_ip = netifaces.ifaddresses(default_iface)[netifaces.AF_INET][0]['addr']
            print(f"CommandsMultiplexer: default nic -> |{default_iface}| , my_ip -> |{my_ip}| ")
        except KeyError as k:
            print(f"CommandsMultiplexer: exception in retrieve my ip -> {k} ")
            my_ip = "0.0.0.0"
        return my_ip

    def get_probe_ip_if_present(self, probe_id):
        with self.probe_ip_lock:
            return self.probe_ip[probe_id] if (probe_id in self.probe_ip) else None
    
    def set_probe_ip(self, probe_id, probe_ip):
        with self.probe_ip_lock:
            self.probe_ip[probe_id] = probe_ip

    def pop_probe_ip(self, probe_id):
        with self.probe_ip_lock:
            self.probe_ip.pop(probe_id, None)

    def get_probe_ip_for_clock_sync_if_present(self, probe_id):
        with self.probe_ip_lock:
            return self.probe_ip_for_clock_sync[probe_id] if (probe_id in self.probe_ip_for_clock_sync) else None
    
    def set_probe_ip_for_clock_sync(self, probe_id, probe_ip_for_clock_sync):
        with self.probe_ip_lock:
            self.probe_ip_for_clock_sync[probe_id] = probe_ip_for_clock_sync
    
    def pop_probe_ip_for_clock_sync(self, probe_id):
        with self.probe_ip_lock:
            self.probe_ip_for_clock_sync.pop(probe_id, None)

    def ask_probe_ip(self, probe_id, sync_clock_ip = None):
        if sync_clock_ip is None:
            probe_ip = self.get_probe_ip_if_present(probe_id = probe_id)
            if probe_ip is not None:
                return probe_ip
            self.event_ask_probe_ip[probe_id] = threading.Event()
            print(f"CommandsMultiplexer: Unknown probe |{probe_id}| IP. Asking...")
            self.root_service_send_command(probe_id, "get_probe_ip", {"coordinator_ip": self.coordinator_ip} )
            self.event_ask_probe_ip[probe_id].wait(timeout = 5)
            # ------------------------------- WAITING FOR PROBE IP RESPONSE -------------------------------
            self.event_ask_probe_ip.pop(probe_id, None)
            return self.get_probe_ip_if_present(probe_id = probe_id)
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
        if interested_result not in self.results_handler_callback:
            self.results_handler_callback[interested_result] = handler
            return "OK" #print(f"CommandsMultiplexer: Registered result handler for [{interested_result}]")
        else:
            return "There is already a registered handler for " + interested_result


    def add_status_callback(self, interested_status, handler):
        if interested_status not in self.status_handler_callback:
            self.status_handler_callback[interested_status] = handler
            return "OK" #print(f"CommandsMultiplexer: Registered status handler for [{interested_status}]")
        else:
            return "There is already a registered handler for " + interested_status
        

    def add_error_callback(self, interested_error, handler):
        if interested_error not in self.error_handler_callback:
            self.error_handler_callback[interested_error] = handler
            return "OK" #print(f"CommandsMultiplexer: Registered status handler for [{interested_status}]")
        else:
            return "There is already a registered handler for " + interested_error
        

    def add_probes_preparer_callback(self, interested_measurement_type, preparer_callback):
        # Be sure that all the "preparer methods" returns a string!
        if interested_measurement_type not in self.probes_preparer_callback:
            self.probes_preparer_callback[interested_measurement_type] = preparer_callback
            #print(f"CommandsMultiplexer: Registered probes preparer for [{interested_measurement_type}]")
            return "OK"
        else:
            return "There is already a probes-preparer for " + interested_measurement_type
    

    def add_measure_stopper_callback(self, interested_measurement_type, stopper_method_callback):
        if interested_measurement_type not in self.measurement_stopper_callback:
            self.measurement_stopper_callback[interested_measurement_type] = stopper_method_callback
            #print(f"CommandsMultiplexer: Registered measurement-stopper for [{interested_measurement_type}]")
            return "OK"
        else:
            return "There is already a measurement-stopper for " + interested_measurement_type
        

    def result_multiplexer(self, probe_sender: str, nested_result):  # invoked by MQTT module -> on_message on RESULT topic
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
        measurement_type = new_measurement.type
        if measurement_type in self.probes_preparer_callback:
            # *** Ensure that all "preparer" methods return exactly three values (triad). ***
            success_message, measurement_as_dict, error_cause = self.probes_preparer_callback[measurement_type](new_measurement)
            if success_message == "OK":
                msm_id = measurement_as_dict["_id"]
                msm_type = measurement_as_dict["type"]
                self.started_measurement[msm_id] = msm_type
                print(f"CommandsMultiplexer: stored msm_id |{msm_id}| , type: |{msm_type}|")
            return success_message, measurement_as_dict, error_cause
        else:
            return "Error", "Check the measurement type", f"Unkown measure type: {measurement_type}"


    def measurement_stop_by_msm_id(self, msm_id_to_stop : str):  # invoked by REST module
        measure_from_db = self.mongo_db.find_measurement_by_id(measurement_id=msm_id_to_stop)
        if isinstance(measure_from_db, ErrorModel):
            return "Error", measure_from_db.error_description, measure_from_db.error_cause
        
        if measure_from_db.state == STARTED_STATE:
            if measure_from_db.type in self.measurement_stopper_callback:
                return self.measurement_stopper_callback[measure_from_db.type](msm_id_to_stop)
            return "Error", "Check the measurement type", f"Unkown measure type: {measure_from_db.type}"
        elif measure_from_db.state == FAILED_STATE:
            return "Error", "Measurement was failed", "Wrong id?"
        elif measure_from_db.state == COMPLETED_STATE:
            return "Error", "Measurement already completed", "Wrong id?"
        else:
            return "Error", f"The measurement has an unknown state -> |{measure_from_db.state}|", "Unkown measure state"        
            

    # Default handler for the root_service probe message reception
    def root_service_default_handler(self, probe_sender, type, payload):
        if type == "state":
            state_info = payload["state"] if ("state" in payload) else None
            if state_info is None:
                print(f"CommandsMultiplexer: root_service -> received state None from probe |{probe_sender}|")
                return
            probe_ip = payload["ip"] if ("ip" in payload) else None
            if (probe_ip is None) and (state_info != "OFFLINE"):
                print(f"CommandsMultiplexer: root_service -> received state -> |{state_info}| from probe |{probe_sender}| without ip")
                return
            probe_ip_for_clock_sync = payload["clock_sync_ip"] if ("clock_sync_ip" in payload) else None
            if (probe_ip_for_clock_sync is None) and (state_info != "OFFLINE"):
                print(f"CommandsMultiplexer: root_service -> received state -> |{state_info}| from probe |{probe_sender}| without ip for clock sync")
                return
            match state_info:
                case "ONLINE":
                    self.set_probe_ip(probe_id = probe_sender, probe_ip = probe_ip)
                    self.set_probe_ip_for_clock_sync(probe_id = probe_sender, probe_ip_for_clock_sync = probe_ip_for_clock_sync)
                    if probe_ip in self.event_ask_probe_ip: # if this message is triggered by an "ask_probe_ip", then signal it
                        self.event_ask_probe_ip[probe_ip].set()
                    json_set_coordinator_ip = {"coordinator_ip": self.coordinator_ip}
                    self.root_service_send_command(probe_sender, "set_coordinator_ip", json_set_coordinator_ip)
                    print(f"CommandsMultiplexer: root_service -> [{probe_sender}] -> state [{payload['state']}] -> IP |{self.probe_ip[probe_sender]}|")
                case "UPDATE":
                    self.set_probe_ip(probe_id = probe_sender, probe_ip = probe_ip)
                    self.set_probe_ip_for_clock_sync(probe_id = probe_sender, probe_ip_for_clock_sync = probe_ip_for_clock_sync)
                    if probe_ip in self.event_ask_probe_ip: # if this message is triggered by an "ask_probe_ip", then signal it
                        self.event_ask_probe_ip[probe_ip].set()
                case "OFFLINE":
                    self.pop_probe_ip(probe_id=probe_sender)
                    self.pop_probe_ip_for_clock_sync(probe_id = probe_sender)
                    print(f"CommandsMultiplexer: root_service -> probe [{probe_sender}] -> state [{state_info}]")
                case _:
                    print(f"CommandsMultiplexer: root_service -> received unknown state_info -> |{state_info}| , from probe -> |{probe_sender}|")


    def root_service_send_command(self, probe_id, command, root_service_payload):
        json_command = {
            "handler": 'root_service',
            "command": command,
            "payload": root_service_payload
        }
        time.sleep(0.3)
        print(f"CommandsMultiplexer: root_service sending to |{probe_id}| , coordinator ip -> |{self.coordinator_ip}|")
        self.mqtt_client.publish_on_command_topic(probe_id = probe_id, complete_command=json.dumps(json_command))
