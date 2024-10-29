import json
from src.modules.mqttModule.mqttClient import MqttClient
from src.modules.iperfCoordinator.iperf_coordinator import Iperf_Coordinator

class CommandsMultiplexer:
    def __init__(self):
        self.results_handler_list = {}
        self.status_handler_list = {}
    
    def add_result_handler(self, interested_result, handler):
        if interested_result not in self.results_handler_list:
            self.results_handler_list[interested_result] = handler
            print(f"Registered result handler for [{interested_result}]")
        else:
            print(f"There is already a registered handler for -> {interested_result}")

    def add_status_handler(self, interested_status, handler):
        if interested_status not in self.status_handler_list:
            self.status_handler_list[interested_status] = handler
            print(f"Registered status handler for [{interested_status}]")
        else:
            print(f"There is already a registered handler for -> {interested_status}")

    def result_multiplexer(self, probe_sender: str, nested_result):
        try:
            nested_json_result = json.loads(nested_result)
            handler = nested_json_result['handler']
            result = nested_json_result['payload']
            if handler in self.results_handler_list:
                self.results_handler_list[handler](probe_sender, result) # Multiplexing
            else:
                print(f"result_multiplexer: no registered handler for {handler}")
        except json.JSONDecodeError as e:
            print(f"result_multiplexer: json exception -> {e}")
            

    def status_multiplexer(self, probe_sender, nested_status):
        try:
            nested_json_status = json.loads(nested_status)
            handler = nested_json_status['handler']
            type = nested_json_status['type']  # This is the type of status message
            payload = nested_json_status['payload']
            if handler in self.status_handler_list:
                self.status_handler_list[handler](probe_sender, type, payload) # Multiplexing
            else:
                print(f"status_multiplexer:: no registered handler for [{handler}]. PRINT: -> {payload}")
        except json.JSONDecodeError as e:
            print(f"CommandsMultiplexer: status_multiplexer:: json exception -> {e}")

probe_ip = {} # da inserire nella classe CoordinatorMeasureX

def online_status_handler(probe_sender, type, payload):
    global probe_ip
    if type == "state":
        if payload["state"] == "ONLINE" or payload["state"] == "UPDATE":
            probe_ip[probe_sender] = payload["ip"]
            print(f"probe_sender [{probe_sender}] -> state [{payload['state']}] -> ip [{probe_ip[probe_sender]}]")
        else:
            probe_ip.pop(probe_sender, None)
            print(f"probe_sender [{probe_sender}] -> state [{payload['state']}]")
    

def main():
    global probe_ip
    commands_multiplexer = CommandsMultiplexer()

    coordinator_mqtt = MqttClient(
        external_status_handler = commands_multiplexer.status_multiplexer, 
        external_results_handler = commands_multiplexer.result_multiplexer)
    iperf_coordinator = Iperf_Coordinator(coordinator_mqtt)

    commands_multiplexer.add_result_handler('iperf', iperf_coordinator.result_handler_received)
    commands_multiplexer.add_status_handler('iperf', iperf_coordinator.status_handler_received)

    while True:
        print("PRESS 0 -> exit")
        print("PRESS 1 -> send role SERVER to probe2")
        print("PRESS 2 -> send role CLIENT to probe2")
        print("PRESS 3 -> send role SERVER to probe4")
        print("PRESS 4 -> send role CLIENT to probe4")
        print("PRESS 5 -> start throughput measurement")
        print("PRESS 6 -> stop iperf SERVER on probe2")
        print("PRESS 7 -> stop iperf SERVER on probe4")
        command = input()
        match command:
            case "1":
                iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe2", role = "Server")
            case "2":
                iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe2", role = "Client", dest_probe="probe4")
            case "3":
                iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe4", role = "Server")
            case "4":
                iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe4", role = "Client", dest_probe = "probe2")
            case "5":
                iperf_coordinator.send_probe_iperf_start()
            case "6":
                iperf_coordinator.send_probe_iperf_stop("probe2")
            case "7":
                iperf_coordinator.send_probe_iperf_stop("probe4")
            case _:
                break
    coordinator_mqtt.disconnect()

if __name__ == "__main__":
    main()
