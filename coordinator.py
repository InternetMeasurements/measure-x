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
def update_measurements_collection_thread_body(mongo_db: MongoDB):
    """
    Thread function that periodically checks and updates the status of measurements in MongoDB.
    
    Args:
        mongo_db (MongoDB): Instance of MongoDB class to interact with the database
        
    Notes:
        - Runs in an infinite loop
        - Checks every SECONDS_OLD_MEASUREMENT/2 interval
        - Sets old measurements as failed if they exceed the time threshold
    """
    while(True):
        updated_as_failed_measurements = mongo_db.set_old_measurements_as_failed()
        print(f"Periodic Thread: Set {updated_as_failed_measurements} measurements as failed. Next check --> {datetime.fromtimestamp(time.time() + SECONDS_OLD_MEASUREMENT/2)}")
        time.sleep(SECONDS_OLD_MEASUREMENT / 2)


def main():
    """
    Main function that initializes and runs the Measure-X coordinator.
    
    The coordinator performs the following tasks:
    - Initializes MongoDB connection using configuration
    - Starts a background thread to monitor measurement status
    - Sets up command multiplexer for handling MQTT messages
    - Initializes various measurement coordinators:
        - iPerf coordinator
        - Ping coordinator  
        - Energy coordinator
        - Age of Information coordinator
        - UDP Ping coordinator
        - Coexistence coordinator
    - Starts REST API server
    - Runs main loop waiting for exit command
    
    Returns:
        None
        
    Notes:
        The function will exit if MongoDB connection fails
    """
    try:
        cl = ConfigLoader(base_path = Path(__file__).parent, file_name="coordinatorConfig.yaml", KEY = MONGO_KEY)
        mongo_db = MongoDB(mongo_config = cl.config)
    except Exception as e:
        print(f"Coordinator: connection failed to connect to MongoDB. -> Exception info: \n{e}")
        return
    

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
    

    rest_server = RestServer(mongo_instance = mongo_db,
                             commands_multiplexer_instance = commands_multiplexer)
    rest_server.start_REST_API_server()

    while True:
        print("PRESS 0 -> exit")
        command = input()
        if command == "0":
            break
    coordinator_mqtt.disconnect()

if __name__ == "__main__":
    main()
