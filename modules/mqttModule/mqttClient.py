import yaml
import paho.mqtt.client as mqtt

"""
    Il file di configurazione sarà uno per ogni client mqtt. Facendo le prove su un'unica macchina, "sono costretto" a definire più
    di un file di configurazione, uno per il coordinator ed uno per ogni probes, in quanto ci sono parametri "personali" per il client mqtt.
    Quindi, per adesso i file config si chiameranno "coordinatorConfig.yaml"... quando poi andrò su raspberry, posso anche rinominarli tutti
    in "config.yaml".
"""

class mqttClient(mqtt.Client):

    def __init__(self):
        self.config = None
        self.probes_command_topic = None

        with open("./modules/mqttModule/coordinatorConfig.yaml") as file:
            self.config = yaml.safe_load(file)

        mqtt_config = self.config['mqtt_client']
        client_id = mqtt_config['client_id']
        broker_ip = mqtt_config['broker']['host']
        broker_port = mqtt_config['broker']['port']
        keep_alive = mqtt_config['broker']['keep_alive']
        self.probes_command_topic = mqtt_config['publishing']['probes_command_topic']

        super().__init__(client_id = client_id)

        self.on_connect = self.connection_success_event_handler
        self.on_message = self.new_message_event_handler
        if(mqtt_config['broker']['login']): # If there is the enabled credentials ...
            self.username_pw_set(
                mqtt_config['credentials']['username'],
                mqtt_config['credentials']['password'])
        
        self.connect(broker_ip, broker_port, keep_alive)
        self.loop_start()

    def connection_success_event_handler(self, client, userdata, flags, rc): 
        # Invoked when the connection to broker has success
        print(f"The broker has accepted the connection...")
        for topic in self.config['mqtt_client']['subscription_topics']:
            self.subscribe(topic)
            print(f"Subscription to topic [{topic}]")

    def new_message_event_handler(self, client, userdata, message):
        # Invoked when a new message has arrived from the broker      
        print(f"Message pusblished on topic: {message.topic} -> {message.payload.decode('utf-8')}")

    def send_probe_command(self, probe_id, command):
        # Invoked when you want to send a command to one probe
        self.publish("probes/" + probe_id + "/" + self.probes_command_topic, command)        

    def disconnect(self):
        # Invoked to inform the broker to release the allocated resources
        self.loop_stop()
        super().disconnect()
        print(f"Disconnected")
