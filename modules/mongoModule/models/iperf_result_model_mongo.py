class IperfResultModelMongo:
    def __init__(self, start_timestamp, source_ip, source_port, destination_ip, destination_port, bytes_received, duration, avg_speed) -> None:
        self._id = None
        self.start_timestamp = start_timestamp
        self.source_ip = source_ip
        self.source_port = source_port
        self.destination_ip = destination_ip
        self.destination_port = destination_port
        self.bytes_received = bytes_received
        self.duration = duration
        self.avg_speed = avg_speed
        self.type = "THROUGHPUT"
        #self.bit_per_seconds = 

        # Continua a leggere tutti i dati di un result. 
        # Impongo che sia il coordinator a memorizzare i dati dei results.