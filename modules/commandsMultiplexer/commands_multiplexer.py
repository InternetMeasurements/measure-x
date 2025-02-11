import json
import time
import netifaces
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from modules.mqttModule.mqtt_client import Mqtt_Client

class CommandsMultiplexer:
    def __init__(self):
        self.results_handler_list = {}
        self.status_handler_list = {}
        self.error_handeler_list = {}
        self.probes_preparer_list = {}
        self.measurement_stopper_list = {}
        self.mqtt_client = None
        self.probe_ip = {}
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
    
    def add_result_handler(self, interested_result, handler):
        if interested_result not in self.results_handler_list:
            self.results_handler_list[interested_result] = handler
            return "OK" #print(f"CommandsMultiplexer: Registered result handler for [{interested_result}]")
        else:
            return "There is already a registered handler for " + interested_result

    def add_status_handler(self, interested_status, handler):
        if interested_status not in self.status_handler_list:
            self.status_handler_list[interested_status] = handler
            return "OK" #print(f"CommandsMultiplexer: Registered status handler for [{interested_status}]")
        else:
            return "There is already a registered handler for " + interested_status
        
    def add_error_handler(self, interested_error, handler):
        if interested_error not in self.error_handeler_list:
            self.error_handeler_list[interested_error] = handler
            return "OK" #print(f"CommandsMultiplexer: Registered status handler for [{interested_status}]")
        else:
            return "There is already a registered handler for " + interested_error
        

    def add_probes_preparer(self, interested_measurement_type, preparer):
        # Be sure that all the "preparer methods" returns a string!
        if interested_measurement_type not in self.probes_preparer_list:
            self.probes_preparer_list[interested_measurement_type] = preparer
            return "OK" #print(f"CommandsMultiplexer: Registered probes preparer for [{interested_measurement_type}]")
        else:
            return "There is already a probes-preparer for " + interested_measurement_type
    

    def add_measurement_stopper(self, interested_measurement_type, stopper_method):
        if interested_measurement_type not in self.measurement_stopper_list:
            self.measurement_stopper_list[interested_measurement_type] = stopper_method
            return "OK" #print(f"CommandsMultiplexer: Registered measurement-stopper for [{interested_measurement_type}]")
        else:
            return "There is already a measurement-stopper for " + interested_measurement_type
        

    def result_multiplexer(self, probe_sender: str, nested_result):  # invoked by mqtt module
        try:
            nested_json_result = json.loads(nested_result)
            handler = nested_json_result['handler']
            result = nested_json_result['payload']
            if handler in self.results_handler_list:
                self.results_handler_list[handler](probe_sender, result) # Multiplexing
            else:
                print(f"CommandsMultiplexer: result_multiplexer: no registered handler for |{handler}|")
        except json.JSONDecodeError as e:
            print(f"CommandsMultiplexer: result_multiplexer: json exception -> {e}")
            
    def status_multiplexer(self, probe_sender, nested_status):  # invoked by mqtt module
        try:
            nested_json_status = json.loads(nested_status)
            handler = nested_json_status['handler']
            type = nested_json_status['type']  # This is the type of status message
            payload = nested_json_status['payload']
            if handler in self.status_handler_list:
                self.status_handler_list[handler](probe_sender, type, payload) # Multiplexing
            else:
                print(f"CommandsMultiplexer: status_multiplexer: no registered handler for |{handler}|. TYPE: {type}|\n-> PRINT: -> {payload}")
        except json.JSONDecodeError as e:
            print(f"CommandsMultiplexer: status_multiplexer: json exception -> {e}")

    def errors_multiplexer(self, probe_sender, nested_error):  # invoked by mqtt module
        try:
            nested_error_json = json.loads(nested_error)
            error_handler = nested_error_json['handler']
            error_payload = nested_error_json['payload']
            if error_handler in self.error_handeler_list:
                self.error_handeler_list[error_handler](probe_sender, error_payload)
            else:
                print(f"CommandsMultiplexer: default error hanlder -> msg from |{probe_sender}| --> {nested_error}")
        except json.JSONDecodeError as e:
            print(f"CommandsMultiplexer: error_multiplexer: json exception -> {e}")
    

    def prepare_probes_to_measure(self, new_measurement : MeasurementModelMongo):  # invoked by REST module
        measurement_type = new_measurement.type
        if measurement_type in self.probes_preparer_list:
            # *** Ensure that all "preparer" methods return exactly three values (triad). ***
            successs_message, measurement_as_dict, error_cause = self.probes_preparer_list[measurement_type](new_measurement)
            if successs_message == "OK":
                msm_id = measurement_as_dict["_id"]
                msm_type = measurement_as_dict["type"]
                self.started_measurement[msm_id] = msm_type
                print(f"CommandsMultiplexer: stored msm_id |{msm_id}| , type: |{msm_type}|")
            return successs_message, measurement_as_dict, error_cause
        else:
            return "Error", "Check the measurement type", f"Unkown measure type: {measurement_type}"


    def measurement_stop_by_msm_id(self, msm_id_to_stop : str):  # invoked by REST module
        if msm_id_to_stop not in self.started_measurement:
            return "Error", "Unknown measurement", f"Measurement id: |{msm_id_to_stop}| not in memory"    
        
        measurement_type = self.started_measurement[msm_id_to_stop]
        if measurement_type in self.measurement_stopper_list:
            return self.measurement_stopper_list[measurement_type](msm_id_to_stop)
        else:
            return "Error", "Check the measurement type", f"Unkown measure type: {measurement_type}"    


    # Default handler for the root_service probe message reception
    def root_service_default_handler(self, probe_sender, type, payload):
        if type == "state":
            if payload["state"] == "ONLINE" or payload["state"] == "UPDATE":
                self.probe_ip[probe_sender] = payload["ip"]
                json_set_coordinator_ip = {"coordinator_ip": self.coordinator_ip}
                self.root_service_send_command(probe_sender, "set_coordinator_ip", json_set_coordinator_ip)
                print(f"CommandsMultiplexer: root_service -> [{probe_sender}] -> state [{payload['state']}] -> IP |{self.probe_ip[probe_sender]}|")
            elif payload["state"] == "OFFLINE":
                self.probe_ip.pop(probe_sender, None)
                print(f"CommandsMultiplexer: root_service -> [{probe_sender}] -> state [{payload['state']}]")


    def root_service_send_command(self, probe_id, command, root_service_payload):
        json_command = {
            "handler": 'root_service',
            "command": command,
            "payload": root_service_payload
        }
        time.sleep(0.5)
        print(f"CommandsMultiplexer: root_service sending to |{probe_id}| , coordinator ip -> |{self.coordinator_ip}|")
        self.mqtt_client.publish_on_command_topic(probe_id = probe_id, complete_command=json.dumps(json_command))
