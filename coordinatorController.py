from modules.iperfClient.iperfController import IperfController
from modules.mqttModule.mqttClient import MqttClient

def main():

    #iperf_controller = IperfController()
    #iperf_controller.run_iperf_repetitions()

    coordinator_mqtt = MqttClient()
    while True:
        command = input()
        if(command == '0'):
            coordinator_mqtt.disconnect()
            break
        else:
            coordinator_mqtt.send_probe_command(probe_id = "probe1", command = "role: Server")
            coordinator_mqtt.send_probe_command(probe_id = "probe2", command = "role: Client")

if __name__ == "__main__":
    main()
