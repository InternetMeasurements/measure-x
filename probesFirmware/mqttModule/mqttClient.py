import yaml
import json
from pathlib import Path
import os
import psutil
import paho.mqtt.client as mqtt
from shared_resources import SharedState

"""
MQTT Client class for probes.
Handles MQTT connection, publishing, and subscription logic for probe devices in the Measure-X system.
"""

VERBOSE = False

class ProbeMqttClient(mqtt.Client):
    """
    MQTT client for probe devices. Manages connection, topics, publishing, and message handling.
    """
    def __init__(self, probe_id, msg_received_handler_callback):
        """
        Initialize the MQTT client, load configuration, set up topics, and connect to the broker.
        """
        self.config = None
        self.probe_id = None
        self.mosquitto_certificate_path = None
        self.status_topic = None
        self.results_topic = None
        self.connected_to_broker = False
        self.external_mqtt_msg_handler = msg_received_handler_callback

        base_path = Path(__file__).parent
        # VECCHIO
        #yaml_path = os.path.join(base_path, probe_id + ".yaml")
        yaml_path = os.path.join(base_path, "probe_mqtt_client_config.yaml")
        with open(yaml_path) as file:
            self.config = yaml.safe_load(file)

        self.config = self.config['mqtt_client']
        self.probe_id = probe_id
        cert_path = self.config['mosquitto_certificate_path']
        self.mosquitto_certificate_path = os.path.join(base_path, cert_path)
        clean_session = self.config['clean_session']
        broker_ip = self.config['broker']['host']
        broker_port = self.config['broker']['port']
        keep_alive = self.config['broker']['keep_alive']

        """ ******************************************************* PROBE TOPICS *******************************************************"""
        self.status_topic = str(self.config['publishing']['status_topic']).replace('PROBE_ID', self.probe_id)
        self.results_topic = str(self.config['publishing']['results_topic']).replace('PROBE_ID', self.probe_id)
        self.error_topic = str(self.config['publishing']['error_topic']).replace('PROBE_ID', self.probe_id)
        """ ****************************************************************************************************************************"""

        super().__init__(client_id = self.probe_id, clean_session = clean_session)

        self.on_connect = self.connection_success_event_handler
        self.on_message = self.message_rcvd_event_handler
        if(self.config['broker']['login']): # If there is the enabled credentials ...
            self.username_pw_set(
                self.config['credentials']['username'],
                self.config['credentials']['password'])
        
        self.tls_set( ca_certs = self.mosquitto_certificate_path,
                       tls_version=mqtt.ssl.PROTOCOL_TLSv1_2)
        
        self.connect(broker_ip, broker_port, keep_alive)
        self.loop_start()

    def connection_success_event_handler(self, client, userdata, flags, rc): 
        """
        Called when the connection to the broker is successful. Subscribes to topics and publishes ONLINE state.
        """
        # Invoked when the connection to broker has success
        if not self.check_return_code(rc):
            self.loop_stop() # the loop_stop() here, ensure that the client stops to polling the broker with connection requests
            return       
        self.publish_probe_state("ONLINE")

        for topic in self.config['subscription_topics']: # For each topic in subscription_topics...
            topic = str(topic).replace("PROBE_ID", self.probe_id) # Substitution the "PROBE_ID" element with the real probe id
            self.subscribe(topic)
            if VERBOSE:
                print(f"{self.probe_id}: Subscription to topic --> [{topic}]")

    def message_rcvd_event_handler(self, client, userdata, message):
        """
        Called when a new message arrives from the broker. Forwards the message to the external handler.
        """
        # Invoked when a new message has arrived from the broker. The handler is CommandsDemultiplexer   
        if VERBOSE: 
            print(f"MQTT {self.probe_id}: Received msg on topic -> | {message.topic} | {message.payload.decode('utf-8')} |")
        self.external_mqtt_msg_handler(message.payload.decode('utf-8'))

    def publish_on_status_topic(self, status):
        """
        Publish a status message to the status topic.
        """
        # Invoked when you want to publish your status
        if not self.connected_to_broker:
            print(f"{self.probe_id}: Not connected to broker!")
            return
        self.publish(
            topic = self.status_topic,
            payload = status,
            qos = self.config['publishing']['qos'],
            retain = self.config['publishing']['retain'] )
        if VERBOSE:
            print(f"MqttClient: sent on topic |{self.status_topic}| -> {status}")
        
    def publish_on_result_topic(self, result):
        """
        Publish a result message to the results topic.
        """
        # Invoked when you want to publish a result
        self.publish(
            topic = self.results_topic,
            payload = result,
            qos = self.config['publishing']['qos'],
            retain = self.config['publishing']['retain'] )
        if VERBOSE:
            print(f"MqttClient: sent on topic |{self.results_topic}| -> {result}")

    def publish_on_error_topic(self, error_msg):
        """
        Publish an error message to the error topic.
        """
        self.publish(
            topic = self.error_topic,
            payload = error_msg,
            qos = self.config['publishing']['qos'],
            retain = self.config['publishing']['retain'] )
        if VERBOSE:
            print(f"MqttClient: sent on topic |{self.error_topic}| -> {error_msg}")
        
    def publish_command_ACK(self, handler, payload):
        """
        Publish an ACK message for a command to the status topic.
        """
        json_ACK = {
            "handler": handler,
            "type" : "ACK",
            "payload": payload
        }
        self.publish_on_status_topic(json.dumps(json_ACK))

    def publish_command_NACK(self, handler, payload):
        """
        Publish a NACK message for a command to the status topic.
        """
        json_NACK = {
            "handler": handler,
            "type" : "NACK",
            "payload": payload
        }
        self.publish_on_status_topic(json.dumps(json_NACK))

    def check_return_code(self, rc):
        """
        Check the MQTT connection return code and print a human-readable message.
        Returns True if connection is successful, False otherwise.
        """
        match rc:
            case 0:
                print(f"{self.probe_id}: The broker has accepted the connection")
                self.connected_to_broker = True
                return True
            case 1:
                print(f"{self.probe_id}: Connection refused, unacceptable protocol version")
            case 2:
                print(f"{self.probe_id}: Connection refused, identifier rejected")
            case 3:
                print(f"{self.probe_id}: Connection refused, server unavailable")
            case 4:
                print(f"{self.probe_id}: Connection refused, bad user name or password")
            case 5:
                print(f"{self.probe_id}: Connection refused, not authorized")
        self.connected_to_broker = False
        return False
    
    def publish_probe_state(self, state):
        """
        Publish the probe's state (ONLINE, UPDATE, OFFLINE) to the status topic, including IP and MAC if relevant.
        """
        shared_state = SharedState.get_instance()   
        json_status = {
            "handler": "root_service",
            "type": "state",
            "payload": {
                "state" : state
            }
        }
        if (state == "ONLINE") or (state == "UPDATE"):
            json_status["payload"]["ip"] = shared_state.get_probe_ip()
            json_status["payload"]["clock_sync_ip"] = shared_state.get_probe_ip_for_clock_sync()
            json_status["payload"]["mac"] = shared_state.get_probe_mac()
        self.publish_on_status_topic(json.dumps(json_status))

    def publish_error(self, handler, payload):
        """
        Publish a generic error message to the error topic.
        """
        json_error = {
            "handler": handler,
            "payload": payload
        }
        self.publish_on_error_topic(json.dumps(json_error))

    def disconnect(self):
        """
        Disconnect from the MQTT broker, publish OFFLINE state, and stop the loop.
        """
        # Invoked to inform the broker to release the allocated resources
        self.publish_probe_state("OFFLINE")
        self.loop_stop()
        super().disconnect()
        self.connected_to_broker = False
        print(f"{self.probe_id}: Disconnected")