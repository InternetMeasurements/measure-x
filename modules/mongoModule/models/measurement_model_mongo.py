from modules.mongoModule.models.coexisting_application_model_mongo import CoexistingApplicationModelMongo
from bson.objectid import ObjectId


class MeasurementModelMongo:
    def __init__(self, description, type, source_probe, dest_probe, source_probe_ip : str, dest_probe_ip : str, _id = None,
                 state = None, start_time = None, gps_source_probe = None, gps_dest_probe = None,
                 coexisting_application = None, stop_time = None, results = None):
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
        self.results = [] if results is None else results


    @staticmethod
    def cast_dict_in_MeasurementModelMongo(measurement_as_dict):
        try:
            type = measurement_as_dict['type']
            source_probe = measurement_as_dict['source_probe']
            dest_probe = measurement_as_dict['dest_probe']
            source_probe_ip = measurement_as_dict['source_probe_ip']
            dest_probe_ip = measurement_as_dict['dest_probe_ip']
        except Exception as e:
            return None
        _id = state = description = start_time = gps_source_probe = gps_dest_probe = coexisting_application = stop_time = results = None 
        if ('_id' in measurement_as_dict):
            _id = measurement_as_dict['_id']
        if 'state' in measurement_as_dict:
            state = measurement_as_dict['state']
        if 'description' in measurement_as_dict:
            description = measurement_as_dict['description']
        if 'start_time' in measurement_as_dict:
            start_time = measurement_as_dict['start_time']
        if 'gps_source_probe' in measurement_as_dict:
            gps_source_probe = measurement_as_dict['gps_source_probe']
        if 'gps_dest_probe' in measurement_as_dict:
            gps_dest_probe = measurement_as_dict['gps_dest_probe']
        if 'coexisting_application' in measurement_as_dict:
            coexisting_application = measurement_as_dict['coexisting_application']
        if 'stop_time' in measurement_as_dict:
            stop_time = measurement_as_dict['stop_time']
        if 'results' in measurement_as_dict:
            results = measurement_as_dict['results']
        measurement_to_return = MeasurementModelMongo(description=description, type=type, source_probe=source_probe, _id=_id,
                                                      dest_probe=dest_probe, source_probe_ip=source_probe_ip, dest_probe_ip=dest_probe_ip,
                                                      state=state, start_time=start_time, gps_source_probe=gps_source_probe, gps_dest_probe=gps_dest_probe,
                                                      coexisting_application=coexisting_application, stop_time=stop_time, results=results)
        return measurement_to_return
    
    def assign_id(self):
        self._id = ObjectId()

    def to_dict(self, to_store = False):
        return {
            '_id' : str(self._id) if not to_store else self._id,
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
            'stop_time': self.stop_time,
            'results': [str(result_id) for result_id in self.results]
        }