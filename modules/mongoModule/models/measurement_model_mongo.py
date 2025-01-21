from modules.mongoModule.models.coexisting_application_model_mongo import CoexistingApplicationModelMongo

class MeasurementModelMongo:
    def __init__(self, description, type, source_probe, dest_probe, source_probe_ip : str, dest_probe_ip : str, _id = None,
                 state = None, start_time = None, gps_source_probe = None, gps_dest_probe = None,
                 coexisting_application = None, stop_time = None):
        self._id = _id
        self.description = description
        self.type = type
        self.state = state
        self.start_time = start_time # This field is setted when the coordinator send the START command
        self.source_probe = source_probe
        self.dest_probe = dest_probe
        self.source_probe_ip = source_probe_ip
        self.dest_probe_ip = dest_probe_ip
        self.gps_source_probe = gps_source_probe
        self.gps_dest_probe = gps_dest_probe
        self.coexisting_application = coexisting_application #CoexistingApplicationModelMongo()
        self.stop_time = stop_time

    @staticmethod
    def cast_dic_in_MeasurementModelMongo(measurement_as_dic):
        _id = measurement_as_dic['_id']
        description = measurement_as_dic['description']
        type = measurement_as_dic['type']
        source_probe = measurement_as_dic['source_probe']
        dest_probe = measurement_as_dic['dest_probe']
        source_probe_ip = measurement_as_dic['source_probe_ip']
        dest_probe_ip = measurement_as_dic['dest_probe_ip']
        state = start_time = gps_source_probe = gps_dest_probe = coexisting_application = stop_time = None 
        if 'state' in measurement_as_dic:
            state = measurement_as_dic['state']
        if 'start_time' in measurement_as_dic:
            start_time = measurement_as_dic['start_time']
        if 'gps_source_probe' in measurement_as_dic:
            gps_source_probe = measurement_as_dic['gps_source_probe']
        if 'gps_dest_probe' in measurement_as_dic:
            gps_dest_probe = measurement_as_dic['gps_dest_probe']
        if 'coexisting_application' in measurement_as_dic:
            coexisting_application = measurement_as_dic['coexisting_application']
        if 'stop_time' in measurement_as_dic:
            stop_time = measurement_as_dic['stop_time']
        measurement_to_return = MeasurementModelMongo(description=description, type=type, source_probe=source_probe, _id=_id,
                                                      dest_probe=dest_probe, source_probe_ip=source_probe_ip, dest_probe_ip=dest_probe_ip,
                                                      state=state, start_time=start_time, gps_source_probe=gps_source_probe, gps_dest_probe=gps_dest_probe,
                                                      coexisting_application=coexisting_application, stop_time=stop_time)
        return measurement_to_return

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
            'coexisting_application': self.coexisting_application,
            'stop_time': self.stop_time
        }
