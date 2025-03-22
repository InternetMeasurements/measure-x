import os
from pathlib import Path
import threading, json
import cbor2, base64
from bson import ObjectId
from modules.mqttModule.mqtt_client import Mqtt_Client
from modules.configLoader.config_loader import ConfigLoader, UDPPING_KEY
from modules.mongoModule.mongoDB import MongoDB, MeasurementModelMongo
from modules.mongoModule.models.udpping_result_model_mongo import UDPPINGResultModelMongo

class UDPPing_Coordinator:
    # This class implement the UDP-PING module to orchestrate the probes to make udp-ping measurements
    def __init__(self, mqtt_client : Mqtt_Client, registration_handler_error_callback, registration_handler_status_callback,
                 registration_handler_result_callback, registration_measure_preparer_callback,
                 ask_probe_ip_mac_callback, registration_measurement_stopper_callback, mongo_db : MongoDB):
        self.mqtt_client = mqtt_client
        self.ask_probe_ip_mac = ask_probe_ip_mac_callback
        self.mongo_db = mongo_db
        self.queued_measurements = {}
        self.events_received_status_from_probe_sender = {}
        self.events_stop_server_ack = {}

        # Requests to commands_multiplexer: handler STATUS registration
        registration_response = registration_handler_status_callback( interested_status = "udpping",
                                                             handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"UDPPING_Coordinator: registered handler for status -> udpping")
        else:
            print(f"UDPPING_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: handler RESULT registration
        registration_response = registration_handler_result_callback(interested_result = "udpping",
                                                            handler = self.handler_received_result)
        if registration_response == "OK" :
            print(f"UDPPING_Coordinator: registered handler for result -> udpping")
        else:
            print(f"UDPPING_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Probes-Preparer registration
        registration_response = registration_measure_preparer_callback(
            interested_measurement_type = "udpping",
            preparer_callback = self.probes_preparer_to_measurements)
        if registration_response == "OK" :
            print(f"UDPPING_Coordinator: registered prepaper for measurements type -> udpping")
        else:
            print(f"UDPPING_Coordinator: registration preparer failed. Reason -> {registration_response}")
        
        # Requests to commands_multiplexer: Measurement-Stopper registration
        registration_response = registration_measurement_stopper_callback(
            interested_measurement_type = "udpping",
            stopper_method_callback = self.udpping_measurement_stopper)
        if registration_response == "OK" :
            print(f"UDPPING_Coordinator: registered measurement stopper for measurements type -> udpping")
        else:
            print(f"UDPPING_Coordinator: registration measurement stopper failed. Reason -> {registration_response}")


    def send_probe_udpping_measure_start(self, probe_sender, msm_id):
        json_ping_start = {
            "handler": "udpping",
            "command": "start",
            "payload": {
                "msm_id":  msm_id
            }
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_ping_start))


    def send_probe_udpping_measure_stop(self, probe_sender, msm_id):
        json_ping_start = {
            "handler": "udpping",
            "command": "stop",
            "payload": {
                "msm_id":  msm_id
            }
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_ping_start))

    
    def send_disable_ntp_service(self, probe_sender, msm_id, probe_ntp_server, probe_server_udpping, role, udpping_parameters):
        json_disable_ntp_service = {
            "handler": "udpping",
            "command": "disable_ntp_service",
            "payload": {
                "msm_id": msm_id,
                "probe_ntp_server": probe_ntp_server,
                "probe_server_udpping": probe_server_udpping,
                "listen_port": udpping_parameters['listen_port'],
                "packets_size": udpping_parameters['packets_size'],
                "packets_number": udpping_parameters['packets_number'],
                "packets_interval": udpping_parameters['packets_interval'],
                "live_mode": udpping_parameters['live_mode'],
                "role": role
                }
            }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_disable_ntp_service))


    def send_enable_ntp_service(self, probe_sender, msm_id, role, listen_port = None):
        # This command, at the end of the measurement, must be sent to the client probe, to re-enable the ntp_sec service.
        # In this case, the last two paramers are not used, so they can be None (ONLY IN THIS SPECIFIC CASE).
        json_enable_ntp_service = {
            "handler": "udpping",
            "command": "enable_ntp_service",
            "payload": {
                "msm_id": msm_id,
                "role": role,
                "listen_port": listen_port
            }
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_enable_ntp_service))


    def handler_received_result(self, probe_sender, result):
        msm_id = result["msm_id"] if "msm_id" in result else None
        if msm_id is None:
            print(f"UDPPingController: received result from probe |{probe_sender}| -> No measure_id provided. IGNORE.")
            return
        self.store_measurement_result(probe_sender = probe_sender, result = result)
        
    
    def handler_received_status(self, probe_sender, type, payload : json):
        msm_id = payload["msm_id"] if "msm_id" in payload else None
        if msm_id is None:
            print(f"UDPPingController: |{type}| from probe |{probe_sender}| -> No measure_id provided. IGNORE.")
            return
        match type:
            case "ACK":
                command_executed_on_probe = payload["command"]
                match command_executed_on_probe:
                    case "start":
                        print(f"UDPPingController: ACK from probe |{probe_sender}|->|start| , measurement_id -> |{msm_id}|")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = "OK"
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "stop":
                        print(f"UDPPingController: ACK from probe |{probe_sender}|->|stop| , measurement_id -> |{msm_id}|")
                        if msm_id in self.events_stop_server_ack:
                            self.events_stop_server_ack[msm_id][1] = "OK"
                            self.events_stop_server_ack[msm_id][0].set()
                    case "disable_ntp_service":
                        print(f"UDPPingController: ACK from probe |{probe_sender}| , command: |{command_executed_on_probe}| , msm_id: |{msm_id}|")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = "OK"
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "enable_ntp_service":
                        print(f"UDPPingController: ACK from probe |{probe_sender}| , command: |{command_executed_on_probe}| , msm_id: |{msm_id}|")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = "OK"
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case _:
                        print(f"UDPPingController: ACK received for unkonwn UDPPING command -> {command_executed_on_probe}")
            case "NACK":
                failed_command = payload["command"]
                reason = payload['reason']
                match failed_command:
                    case "start":
                        print(f"UDPPingController: received NACK for {failed_command} -> reason: {reason}")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = reason
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "disable_ntp_service":
                        print(f"UDPPingController: received NACK for {failed_command} -> reason: {reason}")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = reason
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "enable_ntp_service":
                        print(f"UDPPingController: received NACK for {failed_command} -> reason: {reason}")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = reason
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "run":
                        print(f"UDPPingController: received NACK for {failed_command} -> reason: {reason}")
                        if self.mongo_db.set_measurement_as_failed_by_id(measurement_id=msm_id):
                            print(f"UDPPingController: measure |{msm_id}| setted as failed")
                    case "stop":
                        print(f"UDPPingController: received NACK for {failed_command} -> reason: {reason}")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = reason
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case _:
                        print(f"UDPPingController: NACK received for unkonwn UDPPING command -> {failed_command}")

    def probes_preparer_to_measurements(self, new_measurement : MeasurementModelMongo):
        new_measurement.assign_id()
        msm_id = str(new_measurement._id)

        udpping_parameters = self.get_default_ping_parameters()
        udpping_parameters = self.override_default_parameters(udpping_parameters, new_measurement.parameters)

        source_probe_ip, _ = self.ask_probe_ip_mac(new_measurement.source_probe)
        if source_probe_ip is None:
            return "Error", f"No response from client probe: {new_measurement.source_probe}", "Reponse Timeout"
        dest_probe_ip, _ = self.ask_probe_ip_mac(new_measurement.dest_probe)
        if dest_probe_ip is None:
            return "Error", f"No response from client probe: {new_measurement.dest_probe}", "Reponse Timeout"
        new_measurement.source_probe_ip = source_probe_ip
        new_measurement.dest_probe_ip = dest_probe_ip
        new_measurement.parameters = udpping_parameters # This setting allow to store params in measurement object even if you don't have inserted them.

        dest_probe_ip_for_clock_sync = self.ask_probe_ip_mac(new_measurement.dest_probe, sync_clock_ip = True)
        
        self.events_received_status_from_probe_sender[msm_id] = [threading.Event(), None]
        self.send_enable_ntp_service(probe_sender=new_measurement.dest_probe, msm_id = msm_id,
                                     listen_port = udpping_parameters['listen_port'], role="Server")
        self.events_received_status_from_probe_sender[msm_id][0].wait(timeout = 5)        

        event_enable_msg = self.events_received_status_from_probe_sender[msm_id][1]
        if event_enable_msg == "OK":            
            self.events_received_status_from_probe_sender[msm_id] = [threading.Event(), None]
            self.send_disable_ntp_service(probe_sender = new_measurement.source_probe, probe_ntp_server = dest_probe_ip_for_clock_sync,
                                          msm_id = msm_id,  probe_server_udpping = new_measurement.dest_probe_ip, role = "Client",
                                          udpping_parameters = udpping_parameters)

            self.events_received_status_from_probe_sender[msm_id][0].wait(5)

            event_disable_msg = self.events_received_status_from_probe_sender[msm_id][1]
            if event_disable_msg == "OK":
                self.events_received_status_from_probe_sender[msm_id] = [threading.Event(), None]
                self.send_probe_udpping_measure_start(probe_sender = new_measurement.source_probe, msm_id = msm_id)
                self.events_received_status_from_probe_sender[msm_id][0].wait(timeout = 5)

                event_start_msg = self.events_received_status_from_probe_sender[msm_id][1]
                if event_start_msg == "OK":
                    self.queued_measurements[msm_id] = new_measurement
                    inserted_measurement_id = self.mongo_db.insert_measurement(measure = new_measurement)
                    if inserted_measurement_id is None:
                        print(f"UDPPingController: can't start udpping. Error while storing measurement on Mongo")
                        return "Error", "Can't send start! Error while inserting measurement udpping in mongo", "MongoDB Down?"
                    return "OK", new_measurement.to_dict(), None
                
                self.send_probe_udpping_measure_stop(probe_sender=new_measurement.dest_probe, msm_id=msm_id)
                self.send_probe_udpping_measure_stop(probe_sender=new_measurement.source_probe, msm_id=msm_id)
                if event_start_msg is not None:
                    print(f"Preparer UDPPING: awaked from server conf NACK -> {event_start_msg}")
                    return "Error", f"Probe |{new_measurement.source_probe}| says: {event_start_msg}", ""
                else:
                    print(f"Preparer UDPPING: No response from probe -> |{new_measurement.source_probe}")
                    return "Error", f"No response from Probe: {new_measurement.source_probe}" , "Reponse Timeout"   
        elif event_enable_msg is not None:
            print(f"Preparer UDPPING: awaked from server conf NACK -> {event_enable_msg}")
            self.send_probe_udpping_measure_stop(probe_sender=new_measurement.source_probe, msm_id=msm_id)
            return "Error", f"Probe |{new_measurement.dest_probe}| says: {event_enable_msg}", ""            
        else:
            print(f"Preparer UDPPING: No response from probe -> |{new_measurement.dest_probe}")
            return "Error", f"No response from Probe: {new_measurement.dest_probe}" , "Reponse Timeout"
        
    
    def udpping_measurement_stopper(self, msm_id_to_stop : str):
        if msm_id_to_stop not in self.queued_measurements:
            return "Error", f"Unknown udpping measurement |{msm_id_to_stop}|", "May be failed"
        measurement_to_stop : MeasurementModelMongo = self.queued_measurements[msm_id_to_stop]
        self.events_stop_server_ack[msm_id_to_stop] = [threading.Event(), None]
        # Stop sending to the Server-udpping-Probe
        self.send_probe_udpping_measure_stop(probe_sender = measurement_to_stop.dest_probe, msm_id = msm_id_to_stop)
        self.events_stop_server_ack[msm_id_to_stop][0].wait(5)
        # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK OF STOP COMMAND FROM DEST PROBE (UDPPING-SERVER)
        stop_event_message = self.events_stop_server_ack[msm_id_to_stop][1]
        stop_server_message_error = stop_event_message if (stop_event_message != "OK") else None

        if (stop_server_message_error is not None) and ("MISMATCH" in stop_server_message_error):
            return "Error", f"Probe |{measurement_to_stop.dest_probe}| says: |{stop_server_message_error}|", "Probe already busy for different measurement"

        self.events_stop_server_ack[msm_id_to_stop] = [threading.Event(), None]
        self.send_probe_udpping_measure_stop(probe_sender = measurement_to_stop.source_probe, msm_id = msm_id_to_stop)
        self.events_stop_server_ack[msm_id_to_stop][0].wait(5)
        stop_event_message = self.events_stop_server_ack[msm_id_to_stop][1]

        # Renabling the ntp_sec service on client probe
        self.send_enable_ntp_service(probe_sender=measurement_to_stop.source_probe, msm_id=msm_id_to_stop, role="Client")

        stop_client_message_error = stop_event_message if (stop_event_message != "OK") else None

        if (stop_server_message_error is None) and (stop_client_message_error is None):
            return "OK", f"Measurement {msm_id_to_stop} stopped.", None

        if stop_server_message_error is not None:
            return "Error", f"Probe |{measurement_to_stop.dest_probe}| says: |{stop_server_message_error}|", "UDPPING server may be is down"
        
        if stop_client_message_error is not None:
            return "Error", f"Probe |{measurement_to_stop.source_probe}| says: |{stop_event_message}|", "UDPPING client may be is down"
    

    def store_measurement_result(self, probe_sender, result : json):
        msm_id = result["msm_id"] if "msm_id" in result else None
        if msm_id is None:
            print(f"UDPPingController: received result from probe |{probe_sender}| -> No measure_id provided. IGNORE.")
            return
        c_udpping_b64 = result["c_udpping_b64"] if ("c_udpping_b64" in result) else None
        if c_udpping_b64 is None:
            print(f"UDPPingController: WARNING -> received result without udpping-timeseries , measure_id -> {result['msm_id']}")
            return
        c_udpping = base64.b64decode(c_udpping_b64)
        udpping_result = cbor2.loads(c_udpping)

        mongo_udpping_result = UDPPINGResultModelMongo(
            msm_id = ObjectId(msm_id),
            udpping_result = udpping_result
        )

        result_id = str(self.mongo_db.insert_result(result = mongo_udpping_result))
        if result_id is not None:
            print(f"UDPPingController: result |{result_id}| stored in db")
        else:
            print(f"UDPPingController: error while storing result |{result_id}|")

        if self.mongo_db.update_results_array_in_measurement(msm_id=msm_id):
            print(f"UDPPingController: updated document linking in measure: |{msm_id}|")
        if self.mongo_db.set_measurement_as_completed(msm_id):
            print(f"UDPPingController: measurement |{msm_id}| completed ")
        self.send_probe_udpping_measure_stop(self.queued_measurements[msm_id].dest_probe, msm_id=msm_id)
        self.send_enable_ntp_service(self.queued_measurements[msm_id].source_probe, msm_id=msm_id, role="Client")

    
    def get_default_ping_parameters(self) -> json:
        base_path = os.path.join(Path(__file__).parent)       
        cl = ConfigLoader(base_path= base_path, file_name = "default_parameters.yaml", KEY = UDPPING_KEY)
        json_default_config = cl.config if (cl.config is not None) else {}
        return json_default_config

    def override_default_parameters(self, json_config, measurement_parameters):
        json_overrided_config = json_config
        if (measurement_parameters is not None) and (isinstance(measurement_parameters, dict)):
            if ('packets_size' in measurement_parameters):
                json_overrided_config['packets_size'] = measurement_parameters['packets_size']
            if ('packets_number' in measurement_parameters):
                json_overrided_config['packets_number'] = measurement_parameters['packets_number']
            if ('live_mode' in measurement_parameters):
                json_overrided_config['live_mode'] = measurement_parameters['live_mode']
            if ('listen_port' in measurement_parameters):
                json_overrided_config['listen_port'] = measurement_parameters['listen_port']
            if ('packets_interval' in measurement_parameters):
                packets_interval = measurement_parameters['packets_interval']
                json_overrided_config['packets_interval'] = packets_interval if (packets_interval != 0) else json_config['packets_interval']
        return json_overrided_config