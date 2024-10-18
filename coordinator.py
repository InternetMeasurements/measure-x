from src.modules.mqttModule.mqttClient import MqttClient
from src.modules.iperfCoordinator.iperf_coordinator import Iperf_Coordinator

class CommandsMultiplexer:
    def __init__(self):
        self.msg_handler_list = {}
        self.status_handler_list = []
    
    def add_msg_handler(self, interested_msg, handler):
        if interested_msg not in self.msg_handler_list:
            self.msg_handler_list[interested_msg] = handler
            print(f"Registered handler for {interested_msg}")
        else:
            print(f"There is already a registered handler for -> {interested_msg}")

    def add_status_handler(self, handler):
        self.status_handler_list.append(handler)

    def decode_msg(self, probe_sender: str, complete_msg):
        message_key = (complete_msg.split(':'))[0]
        message_value = (complete_msg.split(':'))[1]

        if message_key in self.msg_handler_list:
            self.msg_handler_list[message_key](probe_sender, message_value)
        else:
            print(f"Multiplexer: no registered handler for {message_key}")

    def status_multiplexer(self, probe_sender, status):
        for handler in self.status_handler_list:
            handler(probe_sender, status)


def main():
    commands_multiplexer = CommandsMultiplexer()

    coordinator_mqtt = MqttClient(
        external_status_handler = commands_multiplexer.status_multiplexer, 
        external_msg_handler = commands_multiplexer.decode_msg)
    iperf_coordinator = Iperf_Coordinator(coordinator_mqtt)

    commands_multiplexer.add_msg_handler('iperf', iperf_coordinator.iperf_msg_received)

    while True:
        print("PRESS 0 -> exit")
        print("PRESS 1 -> send role to probes2: Server role")
        print("PRESS 2 -> send role to probes4: Client role")
        print("PRESS 3 -> start throughput measurement")
        command = input()
        match command:
            case "1":
                iperf_coordinator.send_probe_iperf_role(probe_id = "probe2", role = "Server")
                #iperf_coordinator.send_probe_iperf_role(probe_id = "probe2", role = "Client")
            case "2":
                iperf_coordinator.send_probe_iperf_role(probe_id = "probe4", role = "Client")
            case "3":
                #coordinator_mqtt.send_probe_iperf_start(probe_id = "probe1")
                iperf_coordinator.send_probe_iperf_start(probe_id = "probe4")
                iperf_coordinator.send_probe_iperf_start(probe_id = "probe2")
            case _:
                break
    coordinator_mqtt.disconnect()

if __name__ == "__main__":
    main()
