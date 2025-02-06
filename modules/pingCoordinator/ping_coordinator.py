import json
import time
import threading
from datetime import datetime as dt
from modules.mqttModule.mqtt_client import Mqtt_Client
from bson import ObjectId
from modules.mongoModule.mongoDB import MongoDB, SECONDS_OLD_MEASUREMENT
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from modules.mongoModule.models.ping_result_model_mongo import PingResultModelMongo

class Ping_Coordinator:

    def __init__(self, mqtt_client : Mqtt_Client, registration_handler_status, 
                 registration_handler_result, registration_measure_preparer, mongo_db : MongoDB):
        self.mqtt_client = mqtt_client
        self.mongo_db = mongo_db
        self.events_received_ack_from_probe_sender = {}

        # Requests to commands_multiplexer: handler STATUS registration
        registration_response = registration_handler_status( interested_status = "ping",
                                                             handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"Ping_Coordinator: registered handler for status -> ping")
        else:
            print(f"Ping_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: handler RESULT registration
        registration_response = registration_handler_result(interested_result = "ping",
                                                            handler = self.handler_received_result)
        if registration_response == "OK" :
            print(f"Ping_Coordinator: registered handler for result -> ping")
        else:
            print(f"Ping_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Probes-Preparer registration
        registration_response = registration_measure_preparer(
            interested_measurement_type = "ping",
            preparer = self.probes_preparer_to_measurements)
        if registration_response == "OK" :
            print(f"Ping_Coordinator: registered prepaper for measurements type -> ping")
        else:
            print(f"Ping_Coordinator: registration preparer failed. Reason -> {registration_response}")


    def handler_received_status(self, probe_sender, type, payload : json):
        msm_id = payload["msm_id"] if ("msm_id" in payload) else None
        command = payload["command"] if ("command" in payload) else None
        match type:
            case "ACK":
                if command == "start":
                    self.events_received_ack_from_probe_sender[msm_id][1] = "OK"
                    self.events_received_ack_from_probe_sender[msm_id][0].set()
            case "NACK":
                reason = payload['reason']
                self.events_received_ack_from_probe_sender[msm_id][1] = reason
                self.events_received_ack_from_probe_sender[msm_id][0].set()
                print(f"Ping_Coordinator: probe |{probe_sender}| -> |{command}| -> NACK, reason -> {reason}")
            case _:
                print(f"Ping_Coordinator: received unkown type message -> |{type}|")


    def handler_received_result(self, probe_sender, result: json):
        measure_id = result['msm_id'] if ('msm_id' in result) else None
        if measure_id is None:
            print("Ping_Coordinator: received result wihout measure_id -> IGNORED")
            return
        
        if ((time.time() - result["start_timestamp"]) < SECONDS_OLD_MEASUREMENT):
            if self.store_measurement_result(result = result):
                print(f"Ping_Coordinator: complete the measurement store and update -> {measure_id}")
        else: #Volendo posso anche evitare questo settaggio, perchè ci penserà il thread periodico
            #if self.mongo_db.set_measurement_as_failed_by_id(result['msm_id']):
            print(f"Ping_Coordinator: ignored result. Reason: expired measurement -> {measure_id}")


    def send_probe_ping_start(self, probe_sender, json_payload):
        json_ping_start = {
            "handler": "ping",
            "command": "start",
            "payload": json_payload
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_ping_start))


    def send_probe_ping_stop(self, probe_destination):
        json_ping_stop = {
            "handler": "ping",
            "command": "stop",
            "payload": {}
        }
        self.mqtt_client.publish_on_command_topic(probe_id=probe_destination, complete_command=json.dumps(json_ping_stop))


    def store_measurement_result(self, result : json) -> bool:
        ping_result = PingResultModelMongo(
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
        result_id = str(self.mongo_db.insert_ping_result(result = ping_result))
        if result_id is not None:
            msm_id = result["msm_id"]
            print(f"Ping_Coordinator: result |{result_id}| stored in db")
            if self.mongo_db.update_results_array_in_measurement(msm_id):
                print(f"Ping_Coordinator: updated document linking in measure: |{msm_id}|")
                if self.mongo_db.set_measurement_as_completed(msm_id):
                    self.print_summary_result(measurement_result = result)
                    return True
        print(f"Ping_Coordinator: error while storing result |{result_id}|")
        return False


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


    """    # Questo metodo è quello che diventerà il PREPARER
    def send_start_command(self, probe_sender, probe_receiver, destination_ip, source_ip, packets_number = 4, packets_size = 32):
        self.last_mongo_measurement = MeasurementModelMongo(
            description = "Latency measure with ping tool",
            type = "ping",
            start_time = dt.now(),
            source_probe = probe_sender,
            dest_probe = probe_receiver,
            source_probe_ip = source_ip,
            dest_probe_ip = destination_ip)
        self.last_mongo_measurement._id = self.mongo_db.insert_measurement(self.last_mongo_measurement)
        if self.last_mongo_measurement._id is None:
            print(f"Ping_Coordinator: can't start ping. Error while storing ping measurement on Mongo")
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
    """


    def probes_preparer_to_measurements(self, new_measurement : MeasurementModelMongo):
        DEFAULT_PACKET_NUMBER = 4
        DEFAULT_PACKET_SIZE = 32
        new_measurement.assign_id()
        measurement_id = str(new_measurement._id)

        json_start_payload = {
                "destination_ip": new_measurement.dest_probe_ip,
                "msm_id": measurement_id,
                "packets_number": DEFAULT_PACKET_NUMBER,
                "packets_size": DEFAULT_PACKET_SIZE }
        
        self.events_received_ack_from_probe_sender[measurement_id] = [threading.Event(), None]
        self.send_probe_ping_start(probe_sender = new_measurement.source_probe, json_payload=json_start_payload)

        self.events_received_ack_from_probe_sender[measurement_id][0].wait(timeout = 5)
        # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK FROM SENDER_PROBE (PING INITIATOR)

        probe_sender_event_message = self.events_received_ack_from_probe_sender[measurement_id][1]
        if probe_sender_event_message == "OK": # If the iperf-server configuration went good, then...
            inserted_measurement_id = self.mongo_db.insert_measurement(measure = new_measurement)
            if inserted_measurement_id is None:
                print(f"Ping_Coordinator: can't start ping. Error while storing ping measurement on Mongo")
                return "Error", "Can't send start! Error while inserting measurement ping in mongo", "MongoDB Down?"
            return "OK", new_measurement.to_dict(), None
        elif probe_sender_event_message is not None:
            print(f"Preparer ping: awaked from server conf NACK -> {probe_sender_event_message}")
            return "Error", f"Probe |{new_measurement.source_probe}| says: {probe_sender_event_message}", "State BUSY"            
        else:
            print(f"Preparer ping: No response from probe -> |{new_measurement.source_probe}")
            return "Error", f"No response from Probe: {new_measurement.source_probe}" , "Reponse Timeout"