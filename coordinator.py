import json
from src.modules.mqttModule.mqtt_client import Mqtt_Client
from src.modules.iperfCoordinator.iperf_coordinator import Iperf_Coordinator
from src.modules.pingCoordinator.ping_coordinator import Ping_Coordinator 

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

    coordinator_mqtt = Mqtt_Client(
        external_status_handler = commands_multiplexer.status_multiplexer, 
        external_results_handler = commands_multiplexer.result_multiplexer)
    iperf_coordinator = Iperf_Coordinator(coordinator_mqtt)
    ping_coordinator = Ping_Coordinator(
        mqtt_client=coordinator_mqtt,
        registration_handler_result=commands_multiplexer.add_result_handler, 
        registration_handler_status=commands_multiplexer.add_status_handler)

    commands_multiplexer.add_status_handler('probe_state', online_status_handler)
    commands_multiplexer.add_result_handler('iperf', iperf_coordinator.handler_received_result)
    commands_multiplexer.add_status_handler('iperf', iperf_coordinator.handler_received_status)


    while True:
        print("PRESS 0 -> exit")
        print("PRESS 1 -> start ping from probe2 to probe4")
        print("PRESS 2 -> start ping from probe4 to probe2")
        print("PRESS 3 -> stop ping on probe2")
        print("PRESS 4 -> stop ping on probe4")
        command = input()
        match command:
            case "1":
                # print("PRESS 1 -> send role SERVER to probe2")
                # iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe2", role = "Server")
                probe_ping_starter = "probe2"
                probe_ping_destinarion = "probe4"
                if probe_ping_starter not in probe_ip:
                    print(f"The starter probe {probe_ping_starter} is OFFLINE")
                    continue
                if probe_ping_destinarion not in probe_ip:
                    print(f"The destination probe {probe_ping_destinarion} is OFFLINE")
                    continue
                ping_coordinator.send_start_command(probe_sender = probe_ping_starter,
                                                     destination_ip = probe_ip[probe_ping_destinarion])
            case "2":
                probe_ping_starter = "probe4"
                probe_ping_destinarion = "probe2"
                if probe_ping_starter not in probe_ip:
                    print(f"The starter probe {probe_ping_starter} is OFFLINE")
                    continue
                if probe_ping_destinarion not in probe_ip:
                    print(f"The destination probe {probe_ping_destinarion} is OFFLINE")
                    continue
                ping_coordinator.send_start_command(probe_sender = probe_ping_starter,
                                                     destination_ip = probe_ip[probe_ping_destinarion])
                #print("PRESS 2 -> send role CLIENT to probe2")
                # destination_probe = "probe4"
                # iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe2", role = "Client", dest_probe=destination_probe, dest_probe_ip=probe_ip.get(destination_probe, None))
                """
                    case "3":
                        # print("PRESS 3 -> send role SERVER to probe4")
                        # iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe4", role = "Server")
                    case "4":
                        print("PRESS 4 -> send role CLIENT to probe4")
                        # destination_probe = "probe2"
                        # iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe4", role = "Client", dest_probe = destination_probe, dest_probe_ip=probe_ip.get(destination_probe, None))
                    case "5":
                        # print("PRESS 5 -> start throughput measurement")
                        # iperf_coordinator.send_probe_iperf_start()
                    case "6":
                        # print("PRESS 6 -> stop iperf SERVER on probe2")
                        # iperf_coordinator.send_probe_iperf_stop("probe2")
                    case "7":
                        # print("PRESS 7 -> stop iperf SERVER on probe4")
                        # iperf_coordinator.send_probe_iperf_stop("probe4")
                """
            case "3":
                ping_coordinator.send_stop_command("probe2")
            case "4":
                ping_coordinator.send_stop_command("probe4")
            case _:
                break
    coordinator_mqtt.disconnect()

if __name__ == "__main__":
    main()
