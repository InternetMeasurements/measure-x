import os
import json
from src.modules.mqttModule.mqtt_client import Mqtt_Client

class Ping_Coordinator:
    def __init__(self, mqtt_client : Mqtt_Client, registration_handler_status, registration_handler_result):
        self.mqtt_client = mqtt_client
        # Requests to commands_multiplexer
        registration_response = registration_handler_status(
            interested_status = "ping",
            handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"Ping_Coordinator: registered handler for status -> ping")
        else:
            print(f"Ping_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer
        registration_response = registration_handler_result(
            interested_result = "ping",
            handler = self.handler_received_result)
        if registration_response == "OK" :
            print(f"Ping_Coordinator: registered handler for result -> ping")
        else:
            print(f"Ping_Coordinator: registration handler failed. Reason -> {registration_response}")


    def handler_received_status(self, probe_sender, type, payload : json):
        match type:
            case "NACK":
                command_failed_on_probe = payload["command"]
                reason = payload['reason']
                print(f"Ping_Coordinator: probe |{probe_sender}|->|{command_failed_on_probe}|->NACK, reason->{reason}")
            case _:
                print(f"Ping_Coordinator: received unkown type message -> |{type}|")
        return
    
    def handler_received_result(self, probe_sender, result: json):
        self.store_measurement_result(result = result)
        self.mongo_db.set_measurement_as_completed(self.last_mongo_measurement._id)
        self.print_summary_result(measurement_result = result)
        self.store_measurement_result(probe_sender = probe_sender , result = result)
    
    def send_start_command(self, probe_sender, destination_ip, packets_number = 4, packets_size = 32):
        json_ping_start = {
            "handler": "ping",
            "command": "start",
            "payload": {
                "destination_ip": destination_ip,
                "measurement_id": 0, # ********************* Da capire come scegliere l'id della misurazione
                "packets_number": packets_number,
                "packets_size": packets_size
            }
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_ping_start))

    def send_stop_command(self, probe_destination):
        json_ping_stop = {
            "handler": "ping",
            "command": "stop",
            "payload": {}
        }
        self.mqtt_client.publish_on_command_topic(probe_id=probe_destination, complete_command=json.dumps(json_ping_stop))

    def store_measurement_result(self, probe_sender, result):
        return

    def print_summary_result(self, measurement_result):
        start_timestamp = measurement_result["start_timestamp"]
        measurement_id = measurement_result["measurement_id"]
        source_ip = measurement_result["source"]
        destination_ip = measurement_result["destination"]
        packets_transmitted = measurement_result["packet_transmit"]
        packets_received = measurement_result["packet_receive"]
        packet_loss = measurement_result["packet_loss_count"]
        packet_loss_rate = measurement_result["packet_loss_rate"]
        rtt_min = measurement_result["rtt_min"]
        rtt_avg = measurement_result["rtt_avg"]
        rtt_max = measurement_result["rtt_max"]
        rtt_mdev = measurement_result["rtt_mdev"]

        print("\n****************** SUMMARY ******************")
        print(f"Timestamp: {start_timestamp}")
        print(f"Measurement ID: {measurement_id}")
        print(f"IP sorgente: {source_ip}")
        print(f"IP destinatario: {destination_ip}")
        print(f"Packets trasmitted: {packets_transmitted}")
        print(f"Packets received: {packets_received}")
        print(f"Packets loss: {packet_loss}")
        print(f"Packet loss rate: {packet_loss_rate}")
        print(f"RTT min: {rtt_min}")
        print(f"RTT avg: {rtt_avg}")
        print(f"RTT max: {rtt_max}")
        print(f"RTT mdev: {rtt_mdev}")
        for icmp_reply in measurement_result['icmp_replies']:
            if "destination" in icmp_reply:
                print(f"\t-------------------------\n{icmp_reply}\n")