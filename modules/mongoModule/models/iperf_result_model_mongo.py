class IperfResultModelMongo:
    def __init__(self, 
                 msm_id, repetition_number, start_timestamp,
                 transport_protocol, source_ip, source_port, destination_ip,
                 destination_port, bytes_received, duration, avg_speed):
        self._id = None
        self.msm_id = msm_id
        self.repetition_number = repetition_number
        self.transport_protocol = transport_protocol
        self.start_timestamp = start_timestamp
        self.source_ip = source_ip
        self.source_port = source_port
        self.destination_ip = destination_ip
        self.destination_port = destination_port
        self.bytes_received = bytes_received
        self.duration = duration
        self.avg_speed = avg_speed

    def to_dict(self):
        return {
            'msm_id': self.msm_id,
            'repetition_number': self.repetition_number,
            'transport_protocol': self.transport_protocol,
            'start_timestamp': self.start_timestamp,
            'bytes_received': self.bytes_received,
            'duration': self.duration,
            'avg_speed': self.avg_speed
        }