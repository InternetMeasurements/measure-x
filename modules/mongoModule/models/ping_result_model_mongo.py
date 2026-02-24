

class PingResultModelMongo:
    def __init__(self, msm_id, type, timestamp, rtt_avg, rtt_max, rtt_min, rtt_mdev,
                packets_sent, packets_received, packets_loss_count, packets_loss_rate, icmp_replies,
                timestamp_iso):
        self._id = None
        self.msm_id = msm_id
        self.type = type
        self.timestamp = timestamp
        self.rtt_avg = rtt_avg
        self.rtt_max = rtt_max
        self.rtt_min = rtt_min
        self.rtt_mdev = rtt_mdev
        self.packets_sent = packets_sent
        self.packets_received = packets_received
        self.packets_loss_count = packets_loss_count
        self.packets_loss_rate = packets_loss_rate
        self.icmp_replies = icmp_replies
        self.timestamp_iso = timestamp_iso

        
    def to_dict(self) -> dict:
        return {
            'msm_id': self.msm_id,
            'type': self.type,
            'timestamp': self.timestamp, # start timestamp
            'rtt_avg': self.rtt_avg,
            'rtt_max': self.rtt_max,
            'rtt_min': self.rtt_min,
            'rtt_mdev': self.rtt_mdev,
            'packets_sent': self.packets_sent,
            'packets_received': self.packets_received,
            'packets_loss_count': self.packets_loss_count,
            'packets_loss_rate': self.packets_loss_rate,
            'icmp_replies': self.icmp_replies,
            'timestamp_iso': self.timestamp_iso
        }