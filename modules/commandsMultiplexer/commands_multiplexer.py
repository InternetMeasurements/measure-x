import json
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo

class CommandsMultiplexer:
    def __init__(self):
        self.results_handler_list = {}
        self.status_handler_list = {}
        self.error_handeler_list = {}
        self.probes_preparer_list = {}
    
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
        
    def add_probes_preparer(self, interested_command, preparer):
        if interested_command not in self.probes_preparer_list:
            self.probes_preparer_list[interested_command] = preparer
            return "OK" #print(f"CommandsMultiplexer: Registered probes preparer for [{interested_command}]")
        else:
            return "There is already a registered handler for " + interested_command

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
    
    def prepare_probes_to_measure(self, new_measurement : MeasurementModelMongo ):  # invoked by REST module
        measurement_type = new_measurement.type
        if measurement_type in self.probes_preparer_list:
            return self.probes_preparer_list[measurement_type](new_measurement)
        