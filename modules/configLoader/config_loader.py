import yaml
import os
from types import SimpleNamespace

MONGO_KEY = 'mongo'
MQTT_KEY = 'mqtt_client'
IPERF_SERVER_KEY = 'iperf_server'
IPERF_CLIENT_KEY = 'iperf_client'
PING_KEY = 'ping'
AOI_KEY = 'aoi'

class ConfigLoader:
    def __init__(self, base_path, file_name, KEY):
        self.config = None

        #base_path = Path(__file__).parent
        #yaml_dir = os.path.join(base_path, "coordinator_conf.yaml")
        yaml_dir = os.path.join(base_path, file_name)
        try:
            with open(yaml_dir) as file:
                self.config = yaml.safe_load(file)
            if KEY == MONGO_KEY:
                self.config = SimpleNamespace(**self.config[MONGO_KEY])
            else:
                self.config = self.config[KEY]
            """
            if MONGO_KEY in self.config:
                self.mongo_config = SimpleNamespace(**self.config[MONGO_KEY])
            elif MQTT_KEY in self.config:
                self.mqtt_config = self.config
            elif IPERF_SERVER_KEY in self.config:
                self.iperf_server_config = self.config
            elif IPERF_CLIENT_KEY in self.config:
                self.iperf_client_config = self.config
            elif PING_KEY in self.config:
                self.ping_config = self.config"
            """
        except Exception as e:
            print(f"ConfigLoader: WARNING -> problem with file |{file_name}|")
