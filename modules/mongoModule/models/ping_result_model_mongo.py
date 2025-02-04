

class PingResultModelMongo:
    def __init__(self, msm_id, start_timestamp, rtt_avg, rtt_max, rtt_min, rtt_mdev,
                packets_sent, packets_received, packets_loss_count, packets_loss_rate, icmp_replies):
        self._id = None
        self.msm_id = msm_id
        self.start_timestamp = start_timestamp
        self.rtt_avg = rtt_avg
        self.rtt_max = rtt_max
        self.rtt_min = rtt_min
        self.rtt_mdev = rtt_mdev
        self.packets_sent = packets_sent
        self.packets_received = packets_received
        self.packets_loss_count = packets_loss_count
        self.packets_loss_rate = packets_loss_rate
        self.icmp_replies = icmp_replies
        


    def to_dict(self) -> dict:
        return {
            'msm_id': self.msm_id,
            'start_timestamp': self.start_timestamp,
            'rtt_avg': self.rtt_avg,
            'rtt_max': self.rtt_max,
            'rtt_min': self.rtt_min,
            'rtt_mdev': self.rtt_mdev,
            'packets_sent': self.packets_sent,
            'packets_received': self.packets_received,
            'packets_loss_count': self.packets_loss_count,
            'packets_loss_rate': self.packets_loss_rate,
            'icmp_replies': self.icmp_replies
        }