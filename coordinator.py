import json
from src.modules.mqttModule.mqttClient import MqttClient
from src.modules.iperfCoordinator.iperf_coordinator import Iperf_Coordinator

class CommandsMultiplexer:
    def __init__(self):
        self.results_handler_list = {}
        self.status_handler_list = {"state": self.probe_state_handler}

    def probe_state_handler(self, probe_sender, status):
        print(f"probe_sender [{probe_sender}] -> state [{status['state']}]")
    
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
            result = nested_json_result['result']
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
            status = nested_json_status['status']
            if handler in self.status_handler_list:
                self.status_handler_list[handler](probe_sender, status) # Multiplexing
            else:
                print(f"status_multiplexer:: no registered handler for [{handler}]. PRINT: -> {status}")
        except json.JSONDecodeError as e:
            print(f"status_multiplexer:: json exception -> {e}")


def main():
    commands_multiplexer = CommandsMultiplexer()

    coordinator_mqtt = MqttClient(
        external_status_handler = commands_multiplexer.status_multiplexer, 
        external_results_handler = commands_multiplexer.result_multiplexer)
    iperf_coordinator = Iperf_Coordinator(coordinator_mqtt)

    commands_multiplexer.add_result_handler('iperf', iperf_coordinator.result_handler_received)
    commands_multiplexer.add_status_handler('iperf', iperf_coordinator.status_handler_received)

    while True:
        print("PRESS 0 -> exit")
        print("PRESS 1 -> send role to probes2: Server role")
        print("PRESS 2 -> send role to probes4: Client role")
        print("PRESS 3 -> start throughput measurement")
        command = input()
        match command:
            case "1":
                iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe2", role = "Server")
                #iperf_coordinator.send_probe_iperf_role(probe_id = "probe2", role = "Client")
            case "2":
                iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe4", role = "Client", dest_probe = "probe2")
            case "3":
                #coordinator_mqtt.send_probe_iperf_start(probe_id = "probe1")
                iperf_coordinator.send_probe_iperf_start()
            case _:
                break
    coordinator_mqtt.disconnect()

if __name__ == "__main__":
    main()
