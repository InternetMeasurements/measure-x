import yaml
import paho.mqtt.client as mqtt

"""
    Estensione della classe paho.mqtt per l'utilizzo sulle probes
"""

class mqttClient(mqtt.Client):

    def __init__(self, probe_id):
        self.config = None
        self.probes_command_topic = None
        self.probe_id = None
        self.status_topic = None
        self.msg_topic = None
        self.role = None
        self.connected_to_broker = False

        yaml_path = "./modules/probesFirmware/mqttModule/" + probe_id + ".yaml"
        with open(yaml_path) as file:
            self.config = yaml.safe_load(file)

        self.config = self.config['mqtt_client']
        self.probe_id = self.config['probe_id']
        clean_session = self.config['clean_session']
        broker_ip = self.config['broker']['host']
        broker_port = self.config['broker']['port']
        keep_alive = self.config['broker']['keep_alive']
        self.status_topic = str(self.config['publishing']['status_topic']).replace('PROBE_ID', self.probe_id)
        self.msg_topic = str(self.config['publishing']['message_topic']).replace('PROBE_ID', self.probe_id)

        super().__init__(client_id = self.probe_id, clean_session = clean_session)

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
            self.loop_stop() # the loop_stop() here, ensure that the client stops to polling the broker with connection requests
            return
        
        self.publish_status("ONLINE")
        for topic in self.config['subscription_topics']:
            topic = str(topic).replace("PROBE_ID", self.probe_id) # Substitution the "PROBE_ID" element with the real probe id
            self.subscribe(topic)
            print(f"{self.probe_id}: Subscription to topic --> [{topic}]")

    def message_rcvd_event_handler(self, client, userdata, message):
        # Invoked when a new message has arrived from the broker      
        print(f"{self.probe_id}: Received msg on topic -> | {message.topic} | {message.payload.decode('utf-8')} |")

    def publish_status(self, status):
        # Invoked when you want to publish your status
        if not self.connected_to_broker:
            print(f"{self.probe_id}: Not connected to broker!")
            return
        self.publish(
            topic = self.status_topic,
            payload = status,
            qos = self.config['publishing']['qos'],
            retain = self.config['publishing']['retain'] )
        
    def publish_msg(self, msg):
        # Invoked when you want to publish a msg
        self.publish(
            topic = self.msg_topic,
            payload = msg,
            qos = self.config['publishing']['qos'],
            retain = self.config['publishing']['retain'] )
        
    def check_return_code(self, rc):
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

    def disconnect(self):
        # Invoked to inform the broker to release the allocated resources
        self.loop_stop()
        super().disconnect()
        self.connected_to_broker = False
        print(f"{self.probe_id}: Disconnected")
