
class CoexistingApplicationModelMongo:
    def __init__(self, packets_size = None, packets_number = None, packets_rate = None,
                 socket_port = None, trace_name = None):
        self.packets_size = packets_size
        self.packets_number = packets_number
        self.packets_rate = packets_rate
        self.socket_port = socket_port
        self.trace_name = trace_name
    
    def to_dict(self):
        return {
            "packets_size" : self.packets_size,
            "packets_number": self.packets_number,
            "packets_rate": self.packets_rate,
            "socket_port": self.socket_port,
            "trace_name": self.trace_name
        }
    
    @staticmethod
    def cast_dict_in_CoexistingApplicationModelMongo(dict):
        if ("trace_name" in dict) and (dict["trace_name"] is not None):
            return CoexistingApplicationModelMongo(trace_name=dict["trace_name"])
        
        return CoexistingApplicationModelMongo(packets_size=dict["packets_size"], packets_number=dict["packets_number"],
                                               packets_rate=dict["packets_rate"], socket_port=dict["socket_port"])