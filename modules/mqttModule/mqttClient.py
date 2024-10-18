import yaml
import os
from pathlib import Path
import paho.mqtt.client as mqtt

"""
    ******************************************************* Classe MQTT PER IL COORDINATOR *******************************************************
"""

class MqttClient(mqtt.Client):

    def __init__(self, external_status_handler, external_msg_handler):
        self.config = None
        self.probes_command_topic = None
        base_path = Path(__file__).parent
        yaml_dir = os.path.join(base_path, "coordinatorConfig.yaml")
        with open(yaml_dir) as file:
            self.config = yaml.safe_load(file)

        self.external_msg_handler = external_msg_handler
        self.external_status_handler = external_status_handler
        self.config = self.config['mqtt_client']
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
        
        self.connect(broker_ip, broker_port, keep_alive)
        self.loop_start()

    def connection_success_event_handler(self, client, userdata, flags, rc): 
        # Invoked when the connection to broker has success
        if not self.check_return_code(rc):
            self.loop_stop() # the loop_stop() here, ensure that the client stops to polling the broker with periodic connection requests
            return
        
        for topic in self.config['subscription_topics']:
            self.subscribe(topic)
            print(f"{self.client_id}: Subscription to topic --> [{topic}]")

    def message_rcvd_event_handler(self, client, userdata, message):
        # Invoked when a new message has arrived from the broker      
        print(f"{self.client_id}: Received msg on topic -> | {message.topic} | {message.payload.decode('utf-8')} |")
        probe_sender = (str(message.topic).split('/'))[1]
        if str(message.topic).endswith("msg"):
            self.external_msg_handler(probe_sender, message.payload.decode('utf-8'))
        else:
            self.external_status_handler(probe_sender, message.payload.decode('utf-8'))
            
    def check_return_code(self, rc):
        match rc:
            case 0:
                print(f"{self.client_id}: The broker has accepted the connection")
                self.connected_to_broker = True
                return True
            case 1:
                print(f"{self.client_id}: Connection refused, unacceptable protocol version")
            case 2:
                print(f"{self.client_id}: Connection refused, identifier rejected")
            case 3:
                print(f"{self.client_id}: Connection refused, server unavailable")
            case 4:
                print(f"{self.client_id}: Connection refused, bad user name or password")
            case 5:
                print(f"{self.client_id}: Connection refused, not authorized")
        self.connected_to_broker = False
        return False

    def disconnect(self):
        # Invoked to inform the broker to release the allocated resources
        self.loop_stop()
        super().disconnect()
        print(f"Disconnected")

    def publish_command(self, command, probe_id): 
        complete_command_topic = str(self.probes_command_topic).replace("PROBE_ID", probe_id)
        self.publish(complete_command_topic, command)
