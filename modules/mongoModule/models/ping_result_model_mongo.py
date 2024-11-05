

class PingResultModelMongo:
    def __init__(self, referred_measurement, avg_rtt, max_rtt, min_rtt, packets_sent, packets_received) -> None:
        self._id = None
        self.referred_measurement = referred_measurement
        self.type = type
        self.avg_rtt = avg_rtt
        self.max_rtt = max_rtt
        self.min_rtt = min_rtt
        self.packets_sent = packets_sent
        self.packets_received = packets_received
        


    def to_dict(self) -> dict:
        return {
            'description': self.description,
            'type': self.type,
            'creation_time': self.creation_time,
            'source_probe': self.source_probe,
            'dest_probe': self.dest_probe,
            'gps_source_probe': self.gps_source_probe,
            'gps_dest_probe': self.gps_dest_probe,
            'background_traffic': self.background_traffic,
            'stop_time': self.stop_time
        }