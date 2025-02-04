import threading
import time
from pathlib import Path
from datetime import datetime
from modules.configLoader.config_loader import ConfigLoader
from modules.mqttModule.mqtt_client import Mqtt_Client
from modules.commandsMultiplexer.commands_multiplexer import CommandsMultiplexer
from modules.iperfCoordinator.iperf_coordinator import Iperf_Coordinator
from modules.pingCoordinator.ping_coordinator import Ping_Coordinator 
from modules.mongoModule.mongoDB import MongoDB, SECONDS_OLD_MEASUREMENT, MeasurementModelMongo
from modules.energyModule.energy_coordinator import EnergyCoordinator

from modules.restAPIModule.swagger_server.rest_server import RestServer

from scapy.all import rdpcap, sendp, IP

probe_ip = {} # Here, i will save the couples {"probe_id": "probe_ip"}

# Default handler for the status probe message reception
def online_status_handler(probe_sender, type, payload):
    global probe_ip
    if type == "state":
        if payload["state"] == "ONLINE" or payload["state"] == "UPDATE":
            probe_ip[probe_sender] = payload["ip"]
            print(f"probe_sender [{probe_sender}] -> state [{payload['state']}] -> ip [{probe_ip[probe_sender]}]")
        elif payload["state"] == "OFFLINE":
            probe_ip.pop(probe_sender, None)
            print(f"probe_sender [{probe_sender}] -> state [{payload['state']}]")

# Thread body for the check failed measurements
def update_measurements_collection_thread_body(mongo_db : MongoDB):
    while(True):
        updated_as_failed_measurements = mongo_db.set_old_measurements_as_failed()
        print(f"Periodic Thread: Setted {updated_as_failed_measurements} measurements as failed. Next check --> {datetime.fromtimestamp(time.time() + SECONDS_OLD_MEASUREMENT/2)}")
        time.sleep(SECONDS_OLD_MEASUREMENT / 2)

    

def main():
    global probe_ip
    try:
        cl = ConfigLoader(base_path = Path(__file__).parent, file_name="coordinatorConfig.yaml")
        mongo_db = MongoDB(mongo_config = cl.mongo_config)
    except Exception as e:
        print(f"Coordinator: connection failed to mongo. -> Exception info: \n{e}")
        return
    
    """
    # Codice DEBUG per l'inserimento di una misurazione test
    measure_test = MeasurementModelMongo(description="test measurement", type="test",
                                         source_probe="probe_test", dest_probe="probe_test",
                                         source_probe_ip="192.168.1.1", dest_probe_ip="192.168.1.2")
    measurement_test_id = mongo_db.insert_measurement(measure=measure_test)
    print(f"Stored test measurement: {measurement_test_id}")
    """
    
    measurement_collection_update_thread = threading.Thread(target=update_measurements_collection_thread_body, args=(mongo_db,))
    measurement_collection_update_thread.daemon = True
    measurement_collection_update_thread.start()

    commands_multiplexer = CommandsMultiplexer()
    coordinator_mqtt = Mqtt_Client(
        external_status_handler = commands_multiplexer.status_multiplexer, 
        external_results_handler = commands_multiplexer.result_multiplexer,
        external_errors_handler = commands_multiplexer.errors_multiplexer)
    
    iperf_coordinator = Iperf_Coordinator(
        mqtt = coordinator_mqtt,
        registration_handler_result = commands_multiplexer.add_result_handler,
        registration_handler_status = commands_multiplexer.add_status_handler,
        registration_measure_preparer = commands_multiplexer.add_probes_preparer,
        mongo_db=mongo_db)
    
    ping_coordinator = Ping_Coordinator(
        mqtt_client=coordinator_mqtt,
        registration_handler_result = commands_multiplexer.add_result_handler, 
        registration_handler_status = commands_multiplexer.add_status_handler,
        mongo_db=mongo_db)
    
    energy_coordinator = EnergyCoordinator(
        mqtt_client=coordinator_mqtt,
        registration_handler_error = commands_multiplexer.add_error_handler,
        registration_handler_status = commands_multiplexer.add_status_handler,
        registration_handler_result = commands_multiplexer.add_result_handler,
        mongo_db=mongo_db)

    commands_multiplexer.add_status_handler('probe_state', online_status_handler)

    rest_server = RestServer(mongo_instance = mongo_db,
                             commands_multiplexer_instance = commands_multiplexer)
    rest_server.start_REST_API_server()

    while True:
        print("PRESS 0 -> exit")
        command = input()
        if command == "0":
            break
        """
        print("PRESS 1 -> start ping from probe2 to probe4")
        print("PRESS 2 -> start ping from probe4 to probe2")
        print("PRESS 3 -> stop ping on probe2")
        print("PRESS 4 -> stop ping on probe4")
        print("PRESS 9 to insert a measure ping")
        
        match command:
            case "1":
                print("PRESS 1 -> send role SERVER to probe2")
                iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe2", role = "Server")
            case "2":
                print("PRESS 2 -> send role CLIENT to probe2")
                destination_probe = "probe4"
                iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe2", role = "Client", source_probe_ip = probe_ip.get("probe2"), dest_probe=destination_probe, dest_probe_ip=probe_ip.get(destination_probe, None))
            case "3":
                print("PRESS 3 -> send role SERVER to probe4")
                iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe4", role = "Server")
            case "4":
                print("PRESS 4 -> send role CLIENT to probe4")
                destination_probe = "probe2"
                iperf_coordinator.send_probe_iperf_configuration(probe_id = "probe4", role = "Client", source_probe_ip = probe_ip.get("probe4"), dest_probe = destination_probe, dest_probe_ip=probe_ip.get(destination_probe, None))
            case "5":
                print("PRESS 5 -> start throughput measurement")
                iperf_coordinator.send_probe_iperf_start()
            case "6":
                print("PRESS 6 -> stop iperf SERVER on probe2")
                iperf_coordinator.send_probe_iperf_stop("probe2")
            case "7":
                print("PRESS 7 -> stop iperf SERVER on probe4")
                iperf_coordinator.send_probe_iperf_stop("probe4")
            case "9":
                test_misura = MeasurementModelMongo(description="Misura ping test", type="Ping", source_probe="probe_test", dest_probe="probe_test",
                                                    source_probe_ip="192.168.1.8", dest_probe_ip="192.168.1.8")
                mongo_db.insert_measurement(test_misura)
            case "10":
                delete_count = mongo_db.delete_measurements_by_id("672fb3887189c5212ab6b2be")
                print(f"Ho eliminato {delete_count} measures")
            case "11":
                pcap_file = r"C:/Users/Francesco/Desktop/OnePingPacket.pcap"
                packets = rdpcap(pcap_file)
                for packet in packets:
                    if IP in packet and packet[IP].dst == "192.168.43.1":
                        sendp(packet, iface="Wi-Fi")  # Sostituisci "eth0" con la tua interfaccia di rete
                    #time.sleep(0.1)  # Tempo tra i pacchetti (in secondi)

            case "a":
                print("Consumption test: INA2019 VS Qoitec ACE")
                energy_coordinator.send_check_i2C_command(probe_id = "probe2")
            case "b":
                print("Consumption test: start measurement")
                energy_coordinator.send_start_command(probe_id = "probe2")
            case "c":
                print("Consumption test: stop measurement")
                energy_coordinator.send_stop_command(probe_id = "probe2")
            case _:
                break
    """
    coordinator_mqtt.disconnect()

if __name__ == "__main__":
    main()
