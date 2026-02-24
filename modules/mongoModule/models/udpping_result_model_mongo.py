from bson import ObjectId

class UDPPINGResultModelMongo:
    def __init__(self, msm_id : str, udpping_result, type, timestamp_iso):
        self._id = None
        self.msm_id = msm_id
        self.udpping_result = udpping_result
        self.type = type
        self.timestamp_iso = timestamp_iso


    def to_dict(self):
        return {
            "msm_id": ObjectId(self.msm_id) if isinstance(self.msm_id, str) else self.msm_id,
            "udpping_result": self.udpping_result,
            "type": self.type,
            "timestamp_iso": self.timestamp_iso
        }
