import yaml
import os
from pathlib import Path
from types import SimpleNamespace

class ConfigLoader:
    def __init__(self) -> None:
        self.mongo_config = None

        base_path = Path(__file__).parent
        yaml_dir = os.path.join(base_path, "coordinator_conf.yaml")
        with open(yaml_dir) as file:
            self.config = yaml.safe_load(file)
        if 'mongo' in self.config:
            self.mongo_config = SimpleNamespace(**self.config['mongo'])