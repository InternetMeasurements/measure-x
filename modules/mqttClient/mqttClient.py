import yaml
import paho.mqtt.client as mqtt

class mqttClient:
    def __init__(self):
        self.client = None
        self.config = None
        self.probes_command_topic = None

        with open("./modules/mqttClient/config.yaml") as file:
            self.config = yaml.safe_load(file)
        mqtt_config = self.config['mqtt_client']
        client_id = mqtt_config['client_id']
        broker_ip = mqtt_config['broker']['host']
        broker_port = mqtt_config['broker']['port']
        keep_alive = mqtt_config['broker']['keep_alive']
        self.probes_command_topic = mqtt_config['publishing']['probes_command_topic']

        print("File configurazione mqtt caricato")
        print(f"mqtt_config: {mqtt_config}")

        self.client = mqtt.Client(client_id = client_id)
        self.client.on_connect = self.connection_success_event_handler
        self.client.on_message = self.new_message_event_handler
        if(mqtt_config['broker']['login']): # If there is the enabled credentials ...
            self.client.username_pw_set(
                mqtt_config['credentials']['username'],
                mqtt_config['credentials']['password'])
        
        self.client.connect(broker_ip, broker_port, keep_alive)
        self.client.loop_start()

    def connection_success_event_handler(self, client, userdata, flags, rc): 
        # Invoked when the connection to broker has success
        if(self.client is None):
            return
        print(f"The broker has accepted the connection...")
        for topic in self.config['mqtt_client']['subscription_topics']:
            self.client.subscribe(topic)
            print(f"Subscription to topic [{topic}]")

    def new_message_event_handler(self, client, userdata, message):
        # Invoked when a new message has arrived from the broker
        if(self.client is None):
            return        
        print(f"Message pusblished on topic: {message.topic} -> {message.payload.decode('utf-8')}")

    def publish_message(self, topic, message):
        # Invoked when you want publish a message on a topic
        if(self.client is None):
            return
        self.client.publish(topic, message)

    def send_probe_command(self, probe_id, command):
        # Invoked when you want to send a command to one probe
        self.publish_message("probes/" + probe_id + "/" + self.probes_command_topic, command)        

    def disconnect(self):
        # Invoked to inform the broker to release the allocated resources
        if(self.client is None):
            return
        self.client.loop_stop()
        self.client.disconnect()
        self.client = None
        print(f"Disconnected")
