import json
import time
from datetime import datetime as dt
from modules.mqttModule.mqtt_client import Mqtt_Client
from bson import ObjectId
from modules.mongoModule.mongoDB import MongoDB, SECONDS_OLD_MEASUREMENT
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from modules.mongoModule.models.ping_result_model_mongo import PingResultModelMongo

class Ping_Coordinator:

    def __init__(self, mqtt_client : Mqtt_Client, registration_handler_status, registration_handler_result, mongo_db : MongoDB):
        self.mqtt_client = mqtt_client
        self.mongo_db = mongo_db
        self.last_mongo_measurement = None

        # Requests to CommandsDemultiplexer
        registration_response = registration_handler_status(
            interested_status = "ping",
            handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"Ping_Coordinator: registered handler for status -> ping")
        else:
            print(f"Ping_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to CommandsDemultiplexer
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
        if ((time.time() - result["start_timestamp"]) < SECONDS_OLD_MEASUREMENT):
            self.store_measurement_result(result = result)
            self.mongo_db.set_measurement_as_completed(self.last_mongo_measurement._id)
            self.print_summary_result(measurement_result = result)
        else: #Volendo posso anche evitare questo settaggio, perchè ci penserà il thread periodico
            #if self.mongo_db.set_measurement_as_failed_by_id(result['msm_id']):
            print(f"Ping_Coordinator: ignored result. Reason: expired measurement -> {result['msm_id']}")
    

    def send_start_command(self, probe_sender, probe_receiver, destination_ip, source_ip, packets_number = 4, packets_size = 32):
        self.last_mongo_measurement = MeasurementModelMongo(
            description = "Latency measure with ping tool",
            type = "Ping",
            start_time = dt.now(),
            source_probe = probe_sender,
            dest_probe = probe_receiver,
            source_probe_ip = source_ip,
            dest_probe_ip = destination_ip)
        self.last_mongo_measurement._id = self.mongo_db.insert_measurement(self.last_mongo_measurement)
        if self.last_mongo_measurement._id is None:
            print(f"Iperf_Coordinator: can't start ping. Error while storing ping measurement on Mongo")
            return
        
        json_ping_start = {
            "handler": "ping",
            "command": "start",
            "payload": {
                "destination_ip": destination_ip,
                "msm_id": str(self.last_mongo_measurement._id),
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


    def store_measurement_result(self, result : json):
        mongo_result = PingResultModelMongo(
            msm_id = ObjectId(result["msm_id"]),
            start_timestamp = result["start_timestamp"],
            rtt_avg = result["rtt_avg"],
            rtt_max = result["rtt_max"],
            rtt_min = result["rtt_min"],
            rtt_mdev = result["rtt_mdev"],
            packets_sent = result["packet_transmit"],
            packets_received = result["packet_receive"],
            packets_loss_count = result["packet_loss_count"],
            packets_loss_rate = result["packet_loss_rate"],
            icmp_replies = result["icmp_replies"]
        )
        result_id = str(self.mongo_db.insert_ping_result(result=mongo_result))
        if result_id is not None:
            print(f"Iperf_Coordinator: result |{result_id}| stored in db")
        else:
            print(f"Iperf_Coordinator: error while storing result |{result_id}|")


    def print_summary_result(self, measurement_result):
        start_timestamp = measurement_result["start_timestamp"]
        msm_id = measurement_result["msm_id"]
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

        print("\n****************** PING SUMMARY ******************")
        print(f"Timestamp: {start_timestamp}")
        print(f"Measurement ID: {msm_id}")
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