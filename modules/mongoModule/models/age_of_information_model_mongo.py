from bson import ObjectId

class AgeOfInformationResultModelMongo:
    def __init__(self, msm_id : str, aois, aoi_min, aoi_max):
        self._id = None
        self.msm_id = msm_id
        self.aois = aois
        self.aoi_min = aoi_min
        self.aoi_max = aoi_max


    def to_dict(self):
        return {
            "msm_id": ObjectId(self.msm_id) if isinstance(self.msm_id, str) else self.msm_id,
            "aoi_min": self.aoi_min,
            "aoi_max": self.aoi_max,
            "aois": self.aois
        }
