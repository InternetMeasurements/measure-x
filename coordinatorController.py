from modules.iperfClient.iperfController import IperfController
from modules.mqttModule.mqttClient import MqttClient
from modules.backgroundTrafficModule.backgroundTrafficGenerator import BackgroundTrafficGenerator

def main():

    #iperf_controller = IperfController()
    #iperf_controller.run_iperf_repetitions()

    """
    coordinator_mqtt = MqttClient()
    while True:
        command = input()
        if(command == '0'):
            coordinator_mqtt.disconnect()
            break
        else:
            coordinator_mqtt.send_probe_command(probe_id = "probe1", command = "role: Server")
            coordinator_mqtt.send_probe_command(probe_id = "probe2", command = "role: Client")
    """
    bt_generator = BackgroundTrafficGenerator()
    bt_generator.submit_process("./modules/backgroundTrafficModule/pcap_files/pcapESPMoistrue.pcap")
    bt_generator.execute_process()

if __name__ == "__main__":
    main()
