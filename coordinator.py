import threading
import time, os, sys
from pathlib import Path
from datetime import datetime
from modules.configLoader.config_loader import ConfigLoader, MONGO_KEY
from modules.mqttModule.mqtt_client import Mqtt_Client
from modules.commandsMultiplexer.commands_multiplexer import CommandsMultiplexer
from modules.iperfCoordinator.iperf_coordinator import Iperf_Coordinator
from modules.pingCoordinator.ping_coordinator import Ping_Coordinator 
from modules.mongoModule.mongoDB import MongoDB, SECONDS_OLD_MEASUREMENT
from modules.energyCoordinator.energy_coordinator import EnergyCoordinator
from modules.aoiCoordinator.aoi_coordinator import Age_of_Information_Coordinator
from modules.udppingCoordinator.udpping_coordinator import UDPPing_Coordinator
from modules.coexCoordinator.coex_coordinator import Coex_Coordinator

from modules.restAPIModule.swagger_server.rest_server import RestServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REST_API_PATH = os.path.join(BASE_DIR, 'modules', 'restAPIModule')
sys.path.insert(0, REST_API_PATH)

# Thread body for the check failed measurements
def update_measurements_collection_thread_body(mongo_db : MongoDB):
    while(True):
        updated_as_failed_measurements = mongo_db.set_old_measurements_as_failed()
        print(f"Periodic Thread: Setted {updated_as_failed_measurements} measurements as failed. Next check --> {datetime.fromtimestamp(time.time() + SECONDS_OLD_MEASUREMENT/2)}")
        time.sleep(SECONDS_OLD_MEASUREMENT / 2)


def main():
    try:
        cl = ConfigLoader(base_path = Path(__file__).parent, file_name="coordinatorConfig.yaml", KEY = MONGO_KEY)
        mongo_db = MongoDB(mongo_config = cl.config)
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

    commands_multiplexer = CommandsMultiplexer(mongo_db)
    coordinator_mqtt = Mqtt_Client(
        status_handler_callback = commands_multiplexer.status_multiplexer, 
        results_handler_callback = commands_multiplexer.result_multiplexer,
        errors_handler_callback = commands_multiplexer.errors_multiplexer)
    commands_multiplexer.set_mqtt_client(coordinator_mqtt)

    commands_multiplexer.add_status_callback(interested_status="root_service", handler=commands_multiplexer.root_service_default_handler)
    
    iperf_coordinator = Iperf_Coordinator(
        mqtt = coordinator_mqtt,
        registration_handler_result_callback = commands_multiplexer.add_result_callback,
        registration_handler_status_callback = commands_multiplexer.add_status_callback,
        registration_measure_preparer_callback = commands_multiplexer.add_probes_preparer_callback,
        ask_probe_ip_mac_callback = commands_multiplexer.ask_probe_ip_mac,
        registration_measurement_stopper_callback = commands_multiplexer.add_measure_stopper_callback,
        mongo_db = mongo_db)
    
    ping_coordinator = Ping_Coordinator(
        mqtt_client = coordinator_mqtt,
        registration_handler_result_callback = commands_multiplexer.add_result_callback, 
        registration_handler_status_callback = commands_multiplexer.add_status_callback,
        registration_measure_preparer_callback = commands_multiplexer.add_probes_preparer_callback,
        ask_probe_ip_mac_callback = commands_multiplexer.ask_probe_ip_mac,
        registration_measurement_stopper_callback = commands_multiplexer.add_measure_stopper_callback,
        mongo_db = mongo_db)
    
    energy_coordinator = EnergyCoordinator(
        mqtt_client=coordinator_mqtt,
        registration_handler_status_callback = commands_multiplexer.add_status_callback,
        registration_handler_result_callback = commands_multiplexer.add_result_callback,
        registration_measure_preparer_callback = commands_multiplexer.add_probes_preparer_callback,
        ask_probe_ip_mac_callback = commands_multiplexer.ask_probe_ip_mac,
        registration_measurement_stopper_callback = commands_multiplexer.add_measure_stopper_callback,
        mongo_db = mongo_db)
    
    aoi_coordinator = Age_of_Information_Coordinator(
        mqtt_client=coordinator_mqtt,
        registration_handler_error_callback = commands_multiplexer.add_error_callback,
        registration_handler_status_callback = commands_multiplexer.add_status_callback,
        registration_handler_result_callback = commands_multiplexer.add_result_callback,
        registration_measure_preparer_callback = commands_multiplexer.add_probes_preparer_callback,
        ask_probe_ip_mac_callback = commands_multiplexer.ask_probe_ip_mac,
        registration_measurement_stopper_callback = commands_multiplexer.add_measure_stopper_callback,
        mongo_db = mongo_db
    )

    udpping_coordinator = UDPPing_Coordinator(
        mqtt_client=coordinator_mqtt,
        registration_handler_error_callback = commands_multiplexer.add_error_callback,
        registration_handler_status_callback = commands_multiplexer.add_status_callback,
        registration_handler_result_callback = commands_multiplexer.add_result_callback,
        registration_measure_preparer_callback = commands_multiplexer.add_probes_preparer_callback,
        ask_probe_ip_mac_callback = commands_multiplexer.ask_probe_ip_mac,
        registration_measurement_stopper_callback = commands_multiplexer.add_measure_stopper_callback,
        mongo_db = mongo_db
    )

    coex_coordinator = Coex_Coordinator(
        mqtt_client = coordinator_mqtt,
        registration_handler_error_callback = commands_multiplexer.add_error_callback,
        registration_handler_status_callback = commands_multiplexer.add_status_callback,
        registration_measure_preparer_callback = commands_multiplexer.add_probes_preparer_callback,
        ask_probe_ip_mac_callback = commands_multiplexer.ask_probe_ip_mac,
        registration_measurement_stopper_callback = commands_multiplexer.add_measure_stopper_callback,
        mongo_db = mongo_db)
    
    #mongo_db.calculate_time_differences(seconds_diff=10)
    # Thesis chart -> 67db3d346c29ca74b4be3144 67e043029aefeb88fb06b589
    # STOP OK: 67e14ce90a83f39e8b2768e8
    
    #mongo_db.plot_smoothed("67e959a728a26890f39b2161", series_name = "aois", time_field = "Timestamp", value_field = "AoI",
    #                       with_original = True, with_smoothed = True, granularity = "200ms")

    #mongo_db.find_and_plot("67e264f958d3227f235c1f62", start_coex=6, stop_coex=18, 
    #                       series_name = "timeseries", time_field = "Timestamp", value_field = "Current") # 67dea759dedafef56f68c380 #67d3317d5a32ab6171d3bf63

    
    #commands_multiplexer.add_status_handler('probe_state', online_status_handler)
    # Intermittent: 67e71df29bf739098c564855 not iperf
    # Intermittent: 67e7b95722acb508a7682d2e with iperf SOCKET TCP NOT OPENED
    # Intermittent; 67e7bb6efcde19e50fc8c57a with iperf SOCKET TCP OPENED
    # Intermittent; 67e7c0790a41ab34a202c4a8 with iperf (captured on probe4), traffic incoming
    # Intermittent; 67e7c1690e1bc5bb5f023d74 with iperf (captured on probe4), traffic outgoing

    # AoI senza Coex. Fra probe3 e probe1 lanciato manualmente tcpreplay per vedere se rispetta automatic. il timing -> 67e7cb63f09f698aa49f28ed (Sembra di SI)
    # AoI senza Coex. Fra probe3 e probe1 lanciato manualmente tcpreplay per vedere se rispetta automatic. il timing -> 67e7ce8ea473e07b219e2680 (CONFERMA. SI)

    # tcprewrite + tcpreplay -> AoI con stesso coex di prima con scapy. No delay aggiuntivo --> 67e7e3e24da3a89c886451c2
    # tcprewrite + tcpreplay -> AoI con stesso coex di prima con scapy. No delay aggiuntivo --> 67e7e7ba08cf95aa11481e6f
    # tcprewrite + tcpreplay -> AoI con stesso coex di prima con scapy. No delay aggiuntivo --> 67e7e91517f99032015f1744

    # tcprewrite + tcpreplay -> AoI con stesso coex di prima con scapy. No delay aggiuntivo --> 67e80d9d018e4ff055213fb2 (Perfect) 30 pkts/s
    # tcprewrite + tcpreplay -> AoI con stesso coex di prima con scapy. No delay aggiuntivo --> 67e80e46d934162362cab543 (Perfect) 300 pkts/s
    
    

    """
        Da vedere
        67e6c7b30b606a84fa9b04b6 RATE 5
        67e6c7f80b606a84fa9b04b8 RATE 10
        67e6c8300b606a84fa9b04ba RATE 20
        67e6c8620b606a84fa9b04bc RATE 50
    """

    rest_server = RestServer(mongo_instance = mongo_db,
                             commands_multiplexer_instance = commands_multiplexer)
    rest_server.start_REST_API_server()

    while True:
        print("PRESS 0 -> exit")
        command = input()
        if command == "0":
            break
        # Measure OK 67e178d7c280c68b62dfcbad
    coordinator_mqtt.disconnect()

if __name__ == "__main__":
    main()

    """
    JSON MISURA CHE TESTIMONIA IL MOTIVO PER CUI LO STOP CON DURATION E' LATO PROBES
    {
        _id: ObjectId('67e043029aefeb88fb06b589'),
        description: 'Prova misura',
        type: 'aoi',
        state: 'completed',
        start_time: 1742750467.6435952,
        source_probe: 'probe1',
        dest_probe: 'probe3',
        source_probe_ip: '192.168.43.211',
        dest_probe_ip: '192.168.43.131',
        gps_source_probe: null,
        gps_dest_probe: null,
        coexisting_application: {
            description: 'Coex traffic from tcp_big.pcap',
            source_probe: 'probe4',
            dest_probe: 'probe2',
            source_probe_ip: '192.168.43.152',
            dest_probe_ip: '192.168.43.210',
            packets_size: null,
            packets_number: null,
            packets_rate: null,
            socket_port: 60606,
            trace_name: 'tcp_big',
            delay_start: 6,
            duration: 12
        },
        stop_time: 1742750490.1498997,
        results: [
            ObjectId('67e0431a9aefeb88fb06b58a')
        ],
        parameters: {
            socket_port: 50505,
            packets_rate: 25,
            payload_size: 32
        }
    }
    """