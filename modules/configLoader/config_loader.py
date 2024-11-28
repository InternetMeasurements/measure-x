import yaml
import os
from types import SimpleNamespace

MONGO_KEY = 'mongo'
MQTT_KEY = 'mqtt_client'

class ConfigLoader:
    def __init__(self, base_path, file_name):
        self.mongo_config = None
        self.mqtt_config = None

        #base_path = Path(__file__).parent
        #yaml_dir = os.path.join(base_path, "coordinator_conf.yaml")
        yaml_dir = os.path.join(base_path, file_name)
        with open(yaml_dir) as file:
            self.config = yaml.safe_load(file)
        if MONGO_KEY in self.config:
            self.mongo_config = SimpleNamespace(**self.config[MONGO_KEY])
        if MQTT_KEY in self.config:
            self.mqtt_config = self.config
