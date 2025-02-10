import json
import threading
from probesFirmware.mqttModule.mqttClient import ProbeMqttClient
from shared_resources import shared_state

class CommandsDemultiplexer():
    def __init__(self):
        self.commands_handler_list = {}
        # The CommandsDemultiplexer set as a handler for "root_service" commands, an its internal method
        self.registration_handler_request(interested_command="root_service", handler=self.root_service_command_handler)

        self.mqtt_client = None
        self.event_to_set_in_case_of_root_service_command_reception = None
        #self.status_handler_list = {} # For the future. Is necessary that the probe knows about the Coordinator state? Or another probe state?

    def set_mqtt_client(self, mqtt_client : ProbeMqttClient):
        self.mqtt_client = mqtt_client

    # +------------------ commands_handler_list ------------------+
    # |      COMMAND     |          HANDLER FUNCTION              |
    # +------------------+----------------------------------------+
    # |       iperf      |  iperfController.iperf_command_handler |
    # |       ping       |  pingController.ping_command_handler   |
    # |   bg_generator   |                                        |
    # +------------------+----------------------------------------+

    def registration_handler_request(self, interested_command, handler) -> str:
        if interested_command not in self.commands_handler_list:
            self.commands_handler_list[interested_command] = handler
            return "OK"
        else:
            return "There is already a registered handler for |" + interested_command + "|"

    def decode_command(self, complete_command):
        try:
            nested_command = json.loads(complete_command)
        except Exception as e:
            print(f"CommandsDemultiplexer: Json Command format Wrong! -> {complete_command}")
            return

        print(f"CommandsDemultiplexer: complete_command -> {nested_command} ")
        handler = nested_command["handler"]
        command = nested_command["command"]
        payload = nested_command["payload"]
        if handler in self.commands_handler_list:
            self.commands_handler_list[handler](command, payload)
        else:
            print(f"CommandsDemultiplexer: no registered handler for |{handler}|")

    def root_service_command_handler(self, command, payload):
        global shared_state
        match command:
            case "set_coordinator_ip":
                coordinator_ip = str(payload['coordinator_ip'])
                shared_state.set_coordinator_ip(coordinator_ip = coordinator_ip)
                print(f"CommandsDemultiplexer: coordinator_ip received -> {shared_state.get_coordinator_ip()}")
                if self.event_to_set_in_case_of_root_service_command_reception is not None:
                    self.event_to_set_in_case_of_root_service_command_reception.set()
            case _:
                print(f"CommandsDemultiplexer: root_service handler -> Unkown command -> {command}")
    
    def wait_for_set_coordinator_ip(self):
        # This is a BLOCKING METHOD
        self.event_to_set_in_case_of_root_service_command_reception = threading.Event()
        self.mqtt_client.publish_probe_state("UPDATE")
        #print("CommandsDemultiplexer: waiting for coordinator_ip reception ...")
        self.event_to_set_in_case_of_root_service_command_reception.wait(timeout = 5) 
        # ------------------------- WAIT for ROOT_SERVICE command RECEPTION from COORDINATOR -------------------------
        self.event_to_set_in_case_of_root_service_command_reception = None

