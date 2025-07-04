"""
AoI_Coordinator: Coordinator class for Age of Information (AoI) measurements in Measure-X.
Handles probe orchestration, command dispatch, result collection, and MongoDB integration for AoI experiments.
"""

import os
from pathlib import Path
import threading, json
import cbor2, base64
from bson import ObjectId
from modules.mqttModule.mqtt_client import Mqtt_Client
from modules.configLoader.config_loader import ConfigLoader, AOI_KEY
from modules.mongoModule.mongoDB import MongoDB, MeasurementModelMongo, ErrorModel
from modules.mongoModule.models.age_of_information_model_mongo import AgeOfInformationResultModelMongo

class Age_of_Information_Coordinator:
    """
    Coordinator for Age of Information (AoI) measurements.
    Manages probe orchestration, command dispatch, result collection, and MongoDB integration.
    """
    def __init__(self, mqtt_client : Mqtt_Client, registration_handler_error_callback, registration_handler_status_callback,
                 registration_handler_result_callback, registration_measure_preparer_callback,
                 ask_probe_ip_mac_callback, registration_measurement_stopper_callback, mongo_db : MongoDB):
        """
        Initialize the AoI Coordinator, register all handlers, and set up state variables.
        """
        self.mqtt_client = mqtt_client
        self.ask_probe_ip_mac = ask_probe_ip_mac_callback
        self.mongo_db = mongo_db
        self.queued_measurements = {}
        self.events_received_status_from_probe_sender = {}
        self.events_stop_probe_ack = {}

        # Requests to commands_multiplexer: handler STATUS registration
        registration_response = registration_handler_status_callback( interested_status = "aoi",
                                                             handler = self.handler_received_status)
        if registration_response == "OK" :
            print(f"AoI_Coordinator: registered handler for status -> aoi")
        else:
            print(f"AoI_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: handler RESULT registration
        registration_response = registration_handler_result_callback(interested_result = "aoi",
                                                            handler = self.handler_received_result)
        if registration_response == "OK" :
            print(f"AoI_Coordinator: registered handler for result -> aoi")
        else:
            print(f"AoI_Coordinator: registration handler failed. Reason -> {registration_response}")

        # Requests to commands_multiplexer: Probes-Preparer registration
        registration_response = registration_measure_preparer_callback(
            interested_measurement_type = "aoi",
            preparer_callback = self.probes_preparer_to_measurements)
        if registration_response == "OK" :
            print(f"AoI_Coordinator: registered prepaper for measurements type -> aoi")
        else:
            print(f"AoI_Coordinator: registration preparer failed. Reason -> {registration_response}")
        
        # Requests to commands_multiplexer: Measurement-Stopper registration
        registration_response = registration_measurement_stopper_callback(
            interested_measurement_type = "aoi",
            stopper_method_callback = self.aoi_measurement_stopper)
        if registration_response == "OK" :
            print(f"AoI_Coordinator: registered measurement stopper for measurements type -> aoi")
        else:
            print(f"AoI_Coordinator: registration measurement stopper failed. Reason -> {registration_response}")


    def send_probe_aoi_measure_start(self, probe_sender, msm_id, packets_rate, payload_size):
        """
        Send a command to a probe to start an AoI measurement.
        """
        json_ping_start = {
            "handler": "aoi",
            "command": "start",
            "payload": {
                "msm_id":  msm_id,
                "packets_rate": packets_rate,
                "payload_size": payload_size
            }
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_ping_start))


    def send_probe_aoi_measure_stop(self, probe_sender, msm_id):
        """
        Send a command to a probe to stop an AoI measurement.
        """
        json_ping_start = {
            "handler": "aoi",
            "command": "stop",
            "payload": {
                "msm_id":  msm_id
            }
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_ping_start))

    
    def send_disable_ntp_service(self, probe_sender, probe_ntp_server, probe_server_aoi, msm_id, socket_port, role):
        """
        Send a command to a probe to disable the NTP service (for AoI measurement setup).
        """
        json_disable_ntp_service = {
            "handler": "aoi",
            "command": "disable_ntp_service",
            "payload": {
                "probe_ntp_server": probe_ntp_server,
                "probe_server_aoi": probe_server_aoi,
                "socket_port": socket_port,
                "role": role,
                "msm_id": msm_id }
            }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_disable_ntp_service))


    def send_enable_ntp_service(self, probe_sender, msm_id, role, payload_size = None, socket_port = None):
        """
        Send a command to a probe to enable the NTP service (for AoI measurement teardown or setup).
        """
        # This command, at the end of the measurement, must be sent to the client probe, to re-enable the ntp_sec service.
        # In this case, the last two paramers are not used, so they can be None (ONLY IN THIS SPECIFIC CASE).
        json_enable_ntp_service = {
            "handler": "aoi",
            "command": "enable_ntp_service",
            "payload": {
                "msm_id": msm_id,
                "role": role,
                "socket_port": socket_port,
                "payload_size": payload_size
            }
        }
        self.mqtt_client.publish_on_command_topic(probe_id = probe_sender, complete_command=json.dumps(json_enable_ntp_service))


    def handler_received_result(self, probe_sender, result):
        """
        Handler for results received from probes. Stores the result in the database.
        """
        msm_id = result["msm_id"] if "msm_id" in result else None
        if msm_id is None:
            print(f"AoI_Coordinator: received result from probe |{probe_sender}| -> No measure_id provided. IGNORE.")
            return
        self.store_measurement_result(probe_sender = probe_sender, result = result)
        
    
    def handler_received_status(self, probe_sender, type, payload : json):
        """
        Handler for status messages (ACK/NACK) received from probes. Updates events and handles errors.
        """
        msm_id = payload["msm_id"] if "msm_id" in payload else None
        if msm_id is None:
            print(f"AoI_Coordinator: |{type}| from probe |{probe_sender}| -> No measure_id provided. IGNORE.")
            return
        match type:
            case "ACK":
                command_executed_on_probe = payload["command"]
                match command_executed_on_probe:
                    case "start":
                        print(f"AoI_Coordinator: ACK from probe |{probe_sender}|->|start| , measurement_id -> |{msm_id}|")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = "OK"
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "stop":
                        print(f"AoI_Coordinator: ACK from probe |{probe_sender}|->|stop| , measurement_id -> |{msm_id}|")
                        if msm_id in self.events_stop_probe_ack:
                            self.events_stop_probe_ack[msm_id][1] = "OK"
                            self.events_stop_probe_ack[msm_id][0].set()
                    case "disable_ntp_service":
                        print(f"AoI_Coordinator: ACK from probe |{probe_sender}| , command: |{command_executed_on_probe}| , msm_id: |{msm_id}|")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = "OK"
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "enable_ntp_service":
                        print(f"AoI_Coordinator: ACK from probe |{probe_sender}| , command: |{command_executed_on_probe}| , msm_id: |{msm_id}|")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = "OK"
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case _:
                        print(f"AoI_Coordinator: ACK received for unkonwn AoI command -> {command_executed_on_probe}")
            case "NACK":
                failed_command = payload["command"]
                reason = payload['reason']
                match failed_command:
                    case "start":
                        print(f"AoI_Coordinator: received NACK for {failed_command} -> reason: {reason}")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = reason
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "disable_ntp_service":
                        print(f"AoI_Coordinator: received NACK for {failed_command} -> reason: {reason}")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = reason
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "enable_ntp_service":
                        print(f"AoI_Coordinator: received NACK for {failed_command} -> reason: {reason}")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = reason
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case "run":
                        print(f"AoI_Coordinator: received NACK for {failed_command} -> reason: {reason}")
                        if self.mongo_db.set_measurement_as_failed_by_id(measurement_id=msm_id):
                            print(f"AoI_Coordinator: measure |{msm_id}| setted as failed")
                    case "stop":
                        print(f"AoI_Coordinator: received NACK for {failed_command} -> reason: {reason}")
                        if msm_id in self.events_received_status_from_probe_sender:
                            self.events_received_status_from_probe_sender[msm_id][1] = reason
                            self.events_received_status_from_probe_sender[msm_id][0].set()
                    case _:
                        print(f"AoI_Coordinator: NACK received for unkonwn AoI command -> {failed_command}")

    def probes_preparer_to_measurements(self, new_measurement : MeasurementModelMongo):
        """
        Prepares and orchestrates a new AoI measurement, including probe IP resolution and parameter setup.
        Returns a tuple (status, message, error) depending on the outcome.
        """
        new_measurement.assign_id()
        msm_id = str(new_measurement._id)

        aoi_parameters = self.get_default_ping_parameters()
        aoi_parameters = self.override_default_parameters(aoi_parameters, new_measurement.parameters)

        source_probe_ip, _ = self.ask_probe_ip_mac(new_measurement.source_probe)
        if source_probe_ip is None:
            return "Error", f"No response from client probe: {new_measurement.source_probe}", "Reponse Timeout"
        dest_probe_ip, _ = self.ask_probe_ip_mac(new_measurement.dest_probe) # This call, will trigger the setting of Ip, (both the ip and the sync_clock_ip)
        if dest_probe_ip is None: # This ip is only used to check if the probe is ONLINE. See later, the used ip is the "clock_sync_ip"
            return "Error", f"No response from client probe: {new_measurement.dest_probe}", "Reponse Timeout"
        new_measurement.source_probe_ip = source_probe_ip
        new_measurement.dest_probe_ip = dest_probe_ip
        new_measurement.parameters = aoi_parameters # This setting allow to store params in measurement object even if you don't have inserted them.

        dest_probe_ip_for_clock_sync = self.ask_probe_ip_mac(new_measurement.dest_probe, sync_clock_ip = True)
        
        self.events_received_status_from_probe_sender[msm_id] = [threading.Event(), None]
        self.send_enable_ntp_service(probe_sender=new_measurement.dest_probe, msm_id = msm_id,
                                     socket_port = aoi_parameters['socket_port'], role="Server",
                                     payload_size = aoi_parameters['payload_size'] + 100)
        self.events_received_status_from_probe_sender[msm_id][0].wait(timeout = 5)        

        event_enable_msg = self.events_received_status_from_probe_sender[msm_id][1]        
        if event_enable_msg == "OK":     
            self.events_received_status_from_probe_sender[msm_id] = [threading.Event(), None]
            self.send_disable_ntp_service(probe_sender = new_measurement.source_probe, probe_ntp_server = dest_probe_ip_for_clock_sync,
                                          probe_server_aoi=new_measurement.dest_probe_ip, 
                                          msm_id = msm_id, socket_port = aoi_parameters['socket_port'], role = "Client")
            self.events_received_status_from_probe_sender[msm_id][0].wait(5)

            event_disable_msg = self.events_received_status_from_probe_sender[msm_id][1]
            if event_disable_msg == "OK":
                self.events_received_status_from_probe_sender[msm_id] = [threading.Event(), None]
                self.send_probe_aoi_measure_start(probe_sender = new_measurement.source_probe, msm_id = msm_id, 
                                                  packets_rate = aoi_parameters['packets_rate'], payload_size = aoi_parameters['payload_size'])
                self.events_received_status_from_probe_sender[msm_id][0].wait(timeout = 5)

                event_start_msg = self.events_received_status_from_probe_sender[msm_id][1]
                if event_start_msg == "OK":
                    self.queued_measurements[msm_id] = new_measurement
                    inserted_measurement_id = self.mongo_db.insert_measurement(measure = new_measurement)
                    if inserted_measurement_id is None:
                        print(f"AoI_Coordinator: can't start aoi. Error while storing ping measurement on Mongo")
                        return "Error", "Can't send start! Error while inserting measurement aoi in mongo", "MongoDB Down?"
                    return "OK", new_measurement.to_dict(), None
                
                self.send_probe_aoi_measure_stop(probe_sender=new_measurement.dest_probe, msm_id=msm_id)
                if event_start_msg is not None:
                    print(f"Preparer AoI: awaked from server conf NACK -> {event_start_msg}")
                    return "Error", f"Probe |{new_measurement.source_probe}| says: {event_start_msg}", ""
                else:
                    print(f"Preparer AoI: No response from probe -> |{new_measurement.source_probe}")
                    return "Error", f"No response from Probe: {new_measurement.source_probe}" , "Reponse Timeout"   
        elif event_enable_msg is not None:
            print(f"Preparer AoI: awaked from server conf NACK -> {event_enable_msg}")
            self.send_probe_aoi_measure_stop(probe_sender=new_measurement.source_probe, msm_id=msm_id)
            return "Error", f"Probe |{new_measurement.dest_probe}| says: {event_enable_msg}", ""            
        else:
            print(f"Preparer AoI: No response from probe -> |{new_measurement.dest_probe}")
            return "Error", f"No response from Probe: {new_measurement.dest_probe}" , "Reponse Timeout"
        
    
    def aoi_measurement_stopper(self, msm_id_to_stop : str):
        """
        Stops an ongoing AoI measurement, handling both client and server probes.
        Returns a tuple (status, message, error) depending on the outcome.
        """
        if msm_id_to_stop not in self.queued_measurements:
            return "Error", f"Unknown aoi measurement |{msm_id_to_stop}|", "May be failed"
        measurement_to_stop : MeasurementModelMongo = self.queued_measurements[msm_id_to_stop]
        self.events_stop_probe_ack[msm_id_to_stop] = [threading.Event(), None]
        # Stop sending to the Server-AoI-Probe
        self.send_probe_aoi_measure_stop(probe_sender = measurement_to_stop.source_probe, msm_id = msm_id_to_stop)
        self.events_stop_probe_ack[msm_id_to_stop][0].wait(5)
        # ------------------------------- YOU MUST WAIT (AT MOST 5s) FOR AN ACK/NACK OF STOP COMMAND FROM DEST PROBE (AoI-SERVER)
        stop_event_message = self.events_stop_probe_ack[msm_id_to_stop][1]
        stop_client_message_error = stop_event_message if (stop_event_message != "OK") else None

        if (stop_client_message_error is not None) and ("mismatch" in stop_client_message_error):
            return "Error", f"Probe |{measurement_to_stop.dest_probe}| says: |{stop_client_message_error}|", "Probe already busy for different measurement"

        self.events_stop_probe_ack[msm_id_to_stop] = [threading.Event(), None]
        self.send_probe_aoi_measure_stop(probe_sender = measurement_to_stop.dest_probe, msm_id = msm_id_to_stop)
        self.events_stop_probe_ack[msm_id_to_stop][0].wait(5)
        stop_event_message = self.events_stop_probe_ack[msm_id_to_stop][1]

        # Renabling the ntp_sec service on client probe
        self.send_enable_ntp_service(probe_sender=measurement_to_stop.source_probe, msm_id=msm_id_to_stop, role="Client")

        stop_client_message_error = stop_event_message if (stop_event_message != "OK") else None

        if (stop_client_message_error is None) and (stop_client_message_error is None):
            return "OK", f"Measurement {msm_id_to_stop} stopped.", None

        if stop_client_message_error is not None:
            return "Error", f"Probe |{measurement_to_stop.dest_probe}| says: |{stop_client_message_error}|", "AoI server may be is down"
        
        if stop_client_message_error is not None:
            return "Error", f"Probe |{measurement_to_stop.source_probe}| says: |{stop_event_message}|", "AoI client may be is down"
        
        """
            # Stop sending to the Client-AoI-Probe
            

            stop_event_message = self.events_stop_server_ack[msm_id_to_stop][1]
            if stop_event_message == "OK":
                
            if stop_event_message is not None:
                
            return "Error", f"Can't stop the measurement -> |{msm_id_to_stop}|", f"No response from probe |{measurement_to_stop.dest_probe}|"   
        if stop_event_message is not None:

            
        return "Error", f"Can't stop the measurement -> |{msm_id_to_stop}|", f"No response from probe |{measurement_to_stop.source_probe}|"   
        """
    

    def store_measurement_result(self, probe_sender, result : json):
        """
        Stores the AoI measurement result in the database and updates the measurement status.
        Handles linking results to measurements and marking completion.
        """
        msm_id = result["msm_id"] if "msm_id" in result else None
        if msm_id is None:
            print(f"AoI_Coordinator: received result from probe |{probe_sender}| -> No measure_id provided. IGNORE.")
            return
        
        if msm_id not in self.queued_measurements:
            measure_from_db : MeasurementModelMongo = self.mongo_db.find_measurement_by_id(measurement_id=msm_id)
            if isinstance(measure_from_db, ErrorModel):
                print(f"AoI_Coordinator: received result from a measure not prensent in DB -> {msm_id}")
                return
            self.queued_measurements[msm_id] = measure_from_db

        c_aois_b64 = result["c_aois_b64"] if ("c_aois_b64" in result) else None
        if c_aois_b64 is None:
            print(f"AoI_Coordinator: WARNING -> received result without AoI-timeseries , measure_id -> {result['msm_id']}")
            return
        c_aois = base64.b64decode(c_aois_b64)
        aois = cbor2.loads(c_aois)

        mongo_aoi_result = AgeOfInformationResultModelMongo(
            msm_id = ObjectId(msm_id),
            aois=aois,
            aoi_min = result["aoi_min"],
            aoi_max = result["aoi_max"]
        )

        result_id = self.mongo_db.insert_result(result = mongo_aoi_result)

        if isinstance(result_id, dict):
            if self.mongo_db.update_results_array_in_measurement(msm_id=msm_id, result_id=result_id["_id"]):
                print(f"AoI_Coordinator: updated document linking in measure: |{msm_id}| FORCED")
        else:
            if self.mongo_db.update_results_array_in_measurement(msm_id=msm_id):
                print(f"AoI_Coordinator: updated document linking in measure: |{msm_id}|")
        """
        if result_id is not None:
            print(f"AoI_Coordinator: result |{result_id}| stored in db")
        else:
            print(f"AoI_Coordinator: error while storing result |{result_id}|")
        """     
        
        if self.mongo_db.set_measurement_as_completed(msm_id):
            print(f"AoI_Coordinator: measurement |{msm_id}| completed ")
        self.send_enable_ntp_service(probe_sender=self.queued_measurements[msm_id].source_probe, msm_id=msm_id, role="Client")

    
    def get_default_ping_parameters(self) -> json:
        """
        Loads the default AoI measurement parameters from the configuration file.
        Returns a dictionary of default parameters.
        """
        base_path = os.path.join(Path(__file__).parent)       
        cl = ConfigLoader(base_path= base_path, file_name = "default_parameters.yaml", KEY=AOI_KEY)
        json_default_config = cl.config if (cl.config is not None) else {}
        return json_default_config

    def override_default_parameters(self, json_config, measurement_parameters):
        """
        Overrides the default AoI parameters with those provided in the measurement request.
        Returns the updated configuration dictionary.
        """
        json_overrided_config = json_config
        if (measurement_parameters is not None) and (isinstance(measurement_parameters, dict)):
            if ('socket_port' in measurement_parameters):
                json_overrided_config['socket_port'] = measurement_parameters['socket_port']
            if ('packets_rate' in measurement_parameters):
                packets_rate = measurement_parameters['packets_rate']
                json_overrided_config['packets_rate'] = packets_rate if (packets_rate != 0) else json_config['packets_rate']
            if ('payload_size' in measurement_parameters):
                json_overrided_config['payload_size'] = measurement_parameters['payload_size']
        return json_overrided_config