import json

class CommandsMultiplexer:
    def __init__(self):
        self.results_handler_list = {}
        self.status_handler_list = {}
    
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

    def result_multiplexer(self, probe_sender: str, nested_result):
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
            

    def status_multiplexer(self, probe_sender, nested_status):
        try:
            nested_json_status = json.loads(nested_status)
            handler = nested_json_status['handler']
            type = nested_json_status['type']  # This is the type of status message
            payload = nested_json_status['payload']
            if handler in self.status_handler_list:
                self.status_handler_list[handler](probe_sender, type, payload) # Multiplexing
            else:
                print(f"CommandsMultiplexer: status_multiplexer: no registered handler for |{handler}|. PRINT: -> {payload}")
        except json.JSONDecodeError as e:
            print(f"CommandsMultiplexer: status_multiplexer:: json exception -> {e}")

