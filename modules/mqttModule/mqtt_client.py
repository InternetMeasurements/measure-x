import os
from pathlib import Path
import paho.mqtt.client as mqtt
from modules.configLoader.config_loader import ConfigLoader, MQTT_KEY
"""
    ******************************************************* Class FOR THE MQTT CLIENT COORDINATOR *******************************************************
"""

VERBOSE = False

class Mqtt_Client(mqtt.Client):

    def __init__(self, status_handler_callback, results_handler_callback, errors_handler_callback):
        self.config = None
        self.mosquitto_certificate_path = None
        self.probes_command_topic = None

        #base_path = Path(__file__).parent
        #yaml_dir = os.path.join(base_path, "mqttConfig.yaml")
        #with open(yaml_dir) as file:
            #self.config = yaml.safe_load(file)
        base_path = Path(__file__).parent
        cl = ConfigLoader(base_path= base_path, file_name = 'mqttConfig.yaml', KEY=MQTT_KEY)

        self.external_results_handler = results_handler_callback
        self.external_status_handler = status_handler_callback
        self.external_errors_handler = errors_handler_callback

        self.config = cl.config
        cert_path = self.config['mosquitto_certificate_path']
        self.mosquitto_certificate_path = os.path.join(base_path, cert_path)

        self.client_id = self.config['client_id']
        clean_session = self.config['clean_session']
        broker_ip = self.config['broker']['host']
        broker_port = self.config['broker']['port']
        keep_alive = self.config['broker']['keep_alive']
        self.probes_command_topic = self.config['publishing']['topics']['commands']

        super().__init__(client_id = self.client_id, clean_session = clean_session)

        self.on_connect = self.connection_success_event_handler
        self.on_message = self.message_rcvd_event_handler
        if(self.config['broker']['login']): # If there is the enabled credentials ...
            self.username_pw_set(
                self.config['credentials']['username'],
                self.config['credentials']['password'])
        try:
            self.tls_set( ca_certs = self.mosquitto_certificate_path,
                       tls_version=mqtt.ssl.PROTOCOL_TLSv1_2)
            self.connect(broker_ip, broker_port, keep_alive)
            self.loop_start()
        except Exception as e:
            print(f"MqttClient Exception: not connected to the broker. Reason -> {e}")
        
    def connection_success_event_handler(self, client, userdata, flags, rc): 
        # Invoked when the connection to broker has success
        if not self.check_return_code(rc):
            self.loop_stop() # the loop_stop() here, ensure that the client stops to polling the broker with periodic connection requests
            return
        
        for topic in self.config['subscription_topics']:
            self.subscribe(topic)
            if VERBOSE:
                print(f"MqttClient: Subscription to topic --> [{topic}]")

    def message_rcvd_event_handler(self, client, userdata, message):
        # Invoked when a new message has arrived from the broker      
        #print(f"MQTT: Received msg on topic -> | {message.topic} | "
        probe_sender = (str(message.topic).split('/'))[1]
        if VERBOSE:
            print(f"MqttClient: from topic |{str(message.topic)}| -> |{ message.payload.decode('utf-8')}|")
        if str(message.topic).endswith("results"):
            self.external_results_handler(probe_sender, message.payload.decode('utf-8'))
        elif str(message.topic).endswith("status"):
            self.external_status_handler(probe_sender, message.payload.decode('utf-8'))
        elif str(message.topic).endswith("errors"):
            self.external_errors_handler(probe_sender, message.payload.decode('utf-8'))
        else:
            print(f"MqttClient: topic registered but non handled -> {message.topic}")

    def check_return_code(self, rc):
        match rc:
            case 0:
                if VERBOSE:
                    print(f"MqttClient: The broker has accepted the connection")
                self.connected_to_broker = True
                return True
            case 1:
                print(f"MqttClient: Connection refused, unacceptable protocol version")
            case 2:
                print(f"MqttClient: Connection refused, identifier rejected")
            case 3:
                print(f"MqttClient: Connection refused, server unavailable")
            case 4:
                print(f"MqttClient: Connection refused, bad user name or password")
            case 5:
                print(f"MqttClient: Connection refused, not authorized")
        self.connected_to_broker = False
        return False

    def publish_on_command_topic(self, probe_id, complete_command): 
        complete_command_topic = str(self.probes_command_topic).replace("PROBE_ID", probe_id)
        self.publish(
            topic = complete_command_topic, 
            payload = complete_command,
            qos = self.config['publishing']['qos'],
            retain = self.config['publishing']['retain'] )
        
    def disconnect(self):
        # Invoked to inform the broker to release the allocated resources
        self.loop_stop()
        super().disconnect()
        print(f"MqttClient: Disconnected")
