from bson import ObjectId

class EnergyResultModelMongo:
    def __init__(self, msm_id : str, timeseries, energy, byte_tx, byte_rx, duration):
        self._id = None
        self.msm_id = msm_id
        self.timeseries = timeseries
        self.energy = energy
        self.byte_tx = byte_tx
        self.byte_rx = byte_rx
        self.duration = duration


    def to_dict(self):
        return {
            "msm_id": ObjectId(self.msm_id) if isinstance(self.msm_id, str) else self.msm_id,
            "timeseries": self.timeseries,
            "energy": self.energy,
            "byte_tx": self.byte_tx,
            "byte_rx": self.byte_rx,
            "duration": self.duration,
        }
