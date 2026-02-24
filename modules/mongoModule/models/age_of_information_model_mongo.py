from bson import ObjectId

class AgeOfInformationResultModelMongo:
    def __init__(self, msm_id : str, aois, aoi_min, aoi_max, type, timestamp_iso):
        self._id = None
        self.msm_id = msm_id
        self.aois = aois
        self.aoi_min = aoi_min
        self.aoi_max = aoi_max
        self.type = type
        self.timestamp_iso = timestamp_iso


    def to_dict(self):
        return {
            "msm_id": ObjectId(self.msm_id) if isinstance(self.msm_id, str) else self.msm_id,
            "aoi_min": self.aoi_min,
            "aoi_max": self.aoi_max,
            "aois": self.aois,
            "type": self.type,
            "timestamp_iso": self.timestamp_iso
        }
