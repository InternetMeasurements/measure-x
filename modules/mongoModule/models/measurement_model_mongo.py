from modules.mongoModule.models.coexisting_application_model_mongo import CoexistingApplicationModelMongo

class MeasurementModelMongo:
    def __init__(self, description, type, source_probe, dest_probe, source_probe_ip, dest_probe_ip, 
                 state = None, start_time = None, gps_source_probe = None, gps_dest_probe = None):
        self._id = None
        self.description = description
        self.type = type
        self.state = state
        self.start_time = start_time # This field is setted when the coordinator send the START command
        self.source_probe = source_probe
        self.dest_probe = dest_probe
        self.source_probe_ip = source_probe_ip,
        self.dest_probe_ip = dest_probe_ip,
        self.gps_source_probe = gps_source_probe
        self.gps_dest_probe = gps_dest_probe
        self.coexisting_application = None #CoexistingApplicationModelMongo()
        self.stop_time = None

    def to_dict(self):
        return {
            'description': self.description,
            'type': self.type,
            'state': self.state,
            'start_time': self.start_time,
            'source_probe': self.source_probe,
            'dest_probe': self.dest_probe,
            'source_probe_ip': self.source_probe_ip,
            'dest_probe_ip': self.dest_probe_ip,
            'gps_source_probe': self.gps_source_probe,
            'gps_dest_probe': self.gps_dest_probe,
            'background_traffic': self.background_traffic,
            'stop_time': self.stop_time
        }
