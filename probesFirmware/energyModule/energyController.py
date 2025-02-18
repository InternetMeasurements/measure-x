import os
import json
import base64, cbor2, pandas as pd
import psutil, time
from pathlib import Path
from energyModule.ina219Driver import Ina219Driver, SYNC_OTII_PIN
from mqttModule.mqttClient import ProbeMqttClient
from shared_resources import shared_state

DEFAULT_ENERGY_MEASUREMENT_FOLDER = "energy_measurements"

""" Class that implements the POWER CONSUMPTION measurement funcionality """
class EnergyController:
    def __init__(self, mqtt_client : ProbeMqttClient, 
                 registration_handler_request_function):
        self.mqtt_client = mqtt_client
        try:
            self.driverINA = Ina219Driver()
        except Exception as e:
            self.mqtt_client.publish_error(handler="energy", payload="No energy sensor provided")
            print(f"EnergyController: No energy sensor provided")
            return
        
        # Requests to commands_multiplexer
        registration_response = registration_handler_request_function(
            interested_command = "energy",
            handler = self.energy_command_handler)
        if registration_response != "OK" :
            self.mqtt_client.publish_error(handler = "energy", payload = registration_response)
            print(f"EnergyController: registration handler failed. Reason -> {registration_response}")

        self.bytes_received_at_measure_start = None
        self.byte_trasmitted_at_measure_start = None

        
    def energy_command_handler(self, command : str, payload: json):
        print(f"EnergyController: command -> {command} | payload-> {payload}")
        match command:
            case "check":
                if self.INA_sensor_test() == "PASSED":
                    SYNC_OTII_PIN.on()
                    self.send_energy_ACK(successed_command="check")
                    SYNC_OTII_PIN.off()
                else:
                    self.send_energy_NACK(failed_command="start", error_info="INA219 NOT FOUND", measurement_id=msm_id)
            case "start":
                    msm_id = payload['msm_id'] if 'msm_id' in payload else None
                    if msm_id is None:
                        self.send_energy_NACK(failed_command="start", error_info="No measurement provided")
                        return
                    if self.INA_sensor_test() != "PASSED":
                        self.send_energy_NACK(failed_command="start", error_info="INA219 NOT FOUND", measurement_id=msm_id)
                        return
                    base_path = Path(__file__).parent
                    energy_measurement_folder_path = os.path.join(base_path, DEFAULT_ENERGY_MEASUREMENT_FOLDER)
                    if not os.path.exists(energy_measurement_folder_path):
                        os.makedirs(energy_measurement_folder_path)
                    complete_file_path = os.path.join(energy_measurement_folder_path, msm_id + ".csv")
                    start_msg = self.driverINA.start_current_measurement(filename = complete_file_path)
                    if start_msg != "OK":
                        self.send_energy_NACK(failed_command="start", error_info=start_msg, measurement_id=msm_id)
                    else:
                        netstat = psutil.net_io_counters(pernic=True)
                        default_nic_netstat = netstat[shared_state.default_nic_name]
                        self.bytes_received_at_measure_start =  default_nic_netstat.bytes_recv
                        self.byte_trasmitted_at_measure_start = default_nic_netstat.bytes_sent
                        self.send_energy_ACK(successed_command="start", measurement_id=msm_id)
            case "stop":
                    msm_id = payload['msm_id'] if 'msm_id' in payload else None
                    if msm_id is None:
                        self.send_energy_NACK(failed_command="stop", error_info="No measurement provided")
                        return
                    stop_msg = self.driverINA.stop_current_measurement()
                    if stop_msg != "OK":
                        self.send_energy_NACK(failed_command="stop", error_info=stop_msg, measurement_id=msm_id)
                    else:
                        self.send_energy_ACK(successed_command="stop", measurement_id=msm_id)
                        self.compress_and_publish_energy_result(msm_id = msm_id)
            case _:
                print(f"EnergyController: unkown command -> {command}")
                self.send_energy_NACK(failed_command=command, error_info="Unknown command")


    def compress_and_publish_energy_result(self, msm_id):
        
        base_path = Path(__file__).parent
        energy_measurement_file_path = os.path.join(base_path, DEFAULT_ENERGY_MEASUREMENT_FOLDER, msm_id + ".csv")
        df = pd.read_csv(energy_measurement_file_path)

        # MEASURE DURATION
        start_timestamp = df['Timestamp'].iloc[0]
        stop_timestamp = df['Timestamp'].iloc[-1]
        measure_duration = stop_timestamp - start_timestamp

        # MEASURE ENERGY (J)
        current_mean = df["Current"].mean()
        voltage = self.driverINA.get_bus_voltage()
        energy_joule = current_mean * voltage * measure_duration

        # MEASURE BYTE TX and RX
        netstat = psutil.net_io_counters(pernic=True)
        default_nic_netstat = netstat[shared_state.default_nic_name]
        bytes_received_at_measure_stop =  default_nic_netstat.bytes_recv
        byte_trasmitted_at_measure_stop = default_nic_netstat.bytes_sent
        total_byte_received = bytes_received_at_measure_stop - self.bytes_received_at_measure_start
        total_byte_trasmitted = byte_trasmitted_at_measure_stop - self.byte_trasmitted_at_measure_start
        
        # MEASURE TIMESERIES COMPRESSION
        data = df.to_dict(orient='records')
        compressed_data = cbor2.dumps(data)
        compressed_data_b64 = base64.b64encode(compressed_data).decode("utf-8")

        # MEASURE RESULT MESSAGE
        json_energy_result = {
            "handler": "energy",
            "type": "result",
            "payload": {
                "msm_id": msm_id,
                "energy": energy_joule,
                "c_data_b64": compressed_data_b64,
                "byte_tx": total_byte_trasmitted,
                "byte_rx": total_byte_received,
                "duration": measure_duration
             }
        }
        self.mqtt_client.publish_on_result_topic(result=json.dumps(json_energy_result))
        print(f"EnergyController: compressed and published result of msm -> {msm_id}")
    

    def INA_sensor_test(self):
        test_sensor = self.driverINA.i2C_INA_check()
        return "PASSED" if test_sensor else "NOT PASSED"

    def send_energy_ACK(self, successed_command, measurement_id = None):
        json_ack = { 
            "command" : successed_command,
            "msm_id" : self.last_measurement_id if (measurement_id is None) else measurement_id
            }
        print(f"EnergyController: ACK sending -> {json_ack}")
        self.mqtt_client.publish_command_ACK(handler='energy', payload=json_ack) 
    
    def send_energy_NACK(self, failed_command, error_info, measurement_id = None):
        json_nack = {
            "command" : failed_command,
            "reason" : error_info,
            "msm_id" : self.last_measurement_id if (measurement_id is None) else measurement_id
            }
        print(f"EnergyController: NACK sending -> {json_nack}")
        self.mqtt_client.publish_command_NACK(handler='energy', payload = json_nack) 
        