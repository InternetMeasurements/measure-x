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
        self.print_summary_result(measurement_result = result)
        #self.store_measurement_result(probe_sender, result)
    
    def send_start_command(self, probe_sender, destination_ip, packets_number = 4, packets_size = 32):
        json_ping_start = {
            "handler": "ping",
            "command": "start",
            "payload": {
                "destination_ip": destination_ip,
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
        source_ip = measurement_result["source_ip"]
        destination_ip = measurement_result["destination_ip"]
        bytes_received = measurement_result["bytes_received"]
        duration = measurement_result["duration"]
        avg_speed = measurement_result["avg_speed"]

        print("\n****************** SUMMARY ******************")
        print(f"Timestamp: {start_timestamp}")
        print(f"Measurement ID: {measurement_id}")
        print(f"IP sorgente: {source_ip}")
        print(f"IP destinatario: {destination_ip}")
        print(f"Velocità trasferimento {avg_speed} bits/s")
        print(f"Quantità di byte ricevuti: {bytes_received}")
        print(f"Durata misurazione: {duration} secondi\n")