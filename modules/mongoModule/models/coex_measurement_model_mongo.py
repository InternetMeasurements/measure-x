
class CoexistingApplicationModelMongo:
    def __init__(self, source_probe , dest_probe , description = None,
                 packets_size = None, packets_number = None, packets_rate = None,
                 socket_port = None, trace_name = None, source_probe_ip = None,
                 dest_probe_ip = None, delay_start = None, duration = None):
        self.description = description
        self.source_probe = source_probe
        self.dest_probe = dest_probe
        self.source_probe_ip = source_probe_ip
        self.dest_probe_ip = dest_probe_ip
        self.packets_size = packets_size
        self.packets_number = packets_number
        self.packets_rate = packets_rate
        self.socket_port = socket_port
        self.trace_name = trace_name
        self.delay_start = delay_start
        self.duration = duration
    
    def to_dict(self):
        return {
            "description": self.description,
            "source_probe" : self.source_probe,
            "dest_probe" : self.dest_probe,
            "source_probe_ip" : self.source_probe_ip,
            "dest_probe_ip" : self.dest_probe_ip,
            "packets_size" : self.packets_size,
            "packets_number": self.packets_number,
            "packets_rate": self.packets_rate,
            "socket_port": self.socket_port,
            "trace_name": self.trace_name,
            "delay_start": self.delay_start,
            "duration": self.duration
        }

    
    @staticmethod
    def cast_dict_in_CoexistingApplicationModelMongo(dict : dict):
        if ("trace_name" in dict) and (dict["trace_name"] is not None):
            return CoexistingApplicationModelMongo(source_probe = dict["source_probe"], dest_probe = dict["dest_probe"], 
                                                   trace_name = dict["trace_name"], socket_port = dict.get("socket_port"),
                                                   packets_size = dict.get("packets_size"), source_probe_ip=dict.get("source_probe_ip"),
                                                   dest_probe_ip=dict.get("dest_probe_ip"), delay_start = dict.get("delay_start"),
                                                   description=dict.get("description"), duration=dict.get("duration"))
        
        return CoexistingApplicationModelMongo(source_probe = dict["source_probe"], dest_probe = dict["dest_probe"], 
                                               packets_size=dict.get("packets_size"), packets_number=dict.get("packets_number"),
                                               packets_rate=dict.get("packets_rate"), socket_port=dict.get("socket_port"),
                                               source_probe_ip=dict.get("source_probe_ip"), dest_probe_ip=dict.get("dest_probe_ip"),
                                               delay_start = dict.get("delay_start"), description=dict.get("description"),
                                               duration=dict.get("duration"))