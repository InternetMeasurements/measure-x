from src.modules.iperfClient.iperfController import IperfController
from src.modules.mqttModule.mqttClient import MqttClient
from src.modules.probesFirmware.commandsExecutor.backgroundTrafficModule.backgroundTrafficGenerator import BackgroundTrafficGenerator

def main():

    #iperf_controller = IperfController()
    #iperf_controller.run_iperf_repetitions()

    
    coordinator_mqtt = MqttClient()
    while True:
        print("PRESS 0 -> exit")
        print("PRESS 1 -> send roles to probes")
        print("PRESS 2 -> start iperf on probes")
        command = input()
        match command:
            case "1":
                coordinator_mqtt.send_probe_role(probe_id = "probe1", role = "Server")
                coordinator_mqtt.send_probe_role(probe_id = "probe2", role = "Client")
            case "2":
                #coordinator_mqtt.send_probe_iperf_start(probe_id = "probe1")
                coordinator_mqtt.send_probe_iperf_start(probe_id = "probe2")
            case _:
                break
    coordinator_mqtt.disconnect()


    """
    bt_generator = BackgroundTrafficGenerator()
    bt_generator.submit_process("./modules/backgroundTrafficModule/pcap_files/pcapESPMoistrue.pcap")
    bt_generator.execute_process()
    """
if __name__ == "__main__":
    main()
