from modules.probesFirmware.mqttModule.mqttClient import ProbeMqttClient

def main():
    probe1Mqtt = ProbeMqttClient("probe1")
    probe2Mqtt = ProbeMqttClient("probe2")
    while True:
        command = input()
        if(command == '0'):
            probe1Mqtt.publish_status("OFFLINE")
            probe2Mqtt.publish_status("OFFLINE")
            probe1Mqtt.disconnect()
            probe2Mqtt.disconnect()
            break
        else:
            probe1Mqtt.publish_msg("role?")
            probe2Mqtt.publish_msg("role?")
    return

if __name__ == "__main__":
    main()