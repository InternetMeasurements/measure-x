import json
from src.modules.mqttModule.mqtt_client import Mqtt_Client
from src.modules.commandsMultiplexer.commands_multiplexer import CommandsMultiplexer
from src.modules.iperfCoordinator.iperf_coordinator import Iperf_Coordinator
from src.modules.pingCoordinator.ping_coordinator import Ping_Coordinator 
from src.modules.mongoModule.mongoDB import MongoDB

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
    
    iperf_coordinator = Iperf_Coordinator(
        mqtt = coordinator_mqtt,
        registration_handler_result=commands_multiplexer.add_result_handler,
        registration_handler_status=commands_multiplexer.add_status_handler)
    
    ping_coordinator = Ping_Coordinator(
        mqtt_client=coordinator_mqtt,
        registration_handler_result=commands_multiplexer.add_result_handler, 
        registration_handler_status=commands_multiplexer.add_status_handler)

    commands_multiplexer.add_status_handler('probe_state', online_status_handler)

    db = MongoDB()


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
                                                     destination_ip = probe_ip[probe_ping_destinarion],
                                                     packets_number=8,
                                                     packets_size=1024)
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
                                                     destination_ip = probe_ip[probe_ping_destinarion],
                                                     packets_number=8,
                                                     packets_size=1024
                                                     )
                


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
