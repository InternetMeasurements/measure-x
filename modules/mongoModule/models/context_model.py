from bson import ObjectId

class ContextModelMongo:
    def __init__(self,
                 msm_id, probe_id,
                 rsrp=None, rsrq=None, rssi=None, sinr=None, cqi=None, rssnr=None, ber=None,
                 rat=None, mode=None, pci=None, tac=None, cell_id=None, arfcn=None, band=None, bandwidth=None, plmn=None, operator_name=None, connection_state=None):
                 #raw=None,
        self._id = None
        self.msm_id = msm_id
        self.probe_id = probe_id

        # radio metrics
        self.rsrp = rsrp
        self.rsrq = rsrq
        self.rssi = rssi
        self.sinr = sinr
        self.cqi = cqi
        self.rssnr = rssnr
        self.ber = ber

        # access / cell
        self.rat = rat
        self.mode = mode
        self.pci = pci
        self.tac = tac
        self.cell_id = cell_id
        self.arfcn = arfcn
        self.band = band
        self.bandwidth = bandwidth
        self.plmn = plmn
        self.operator_name = operator_name
        self.connection_state = connection_state

        # Entire raw dict
        # self.raw = raw


    def to_dict(self):
        return {
            "msm_id": ObjectId(self.msm_id) if isinstance(self.msm_id, str) else self.msm_id,
            "probe_id": self.probe_id,

            # radio metrics
            "rsrp": self.rsrp,
            "rsrq": self.rsrq,
            "rssi": self.rssi,
            "sinr": self.sinr,
            "cqi": self.cqi,
            "rssnr": self.rssnr,
            "ber": self.ber,

            # access / cell
            "rat": self.rat,
            "mode": self.mode,
            "pci": self.pci,
            "tac": self.tac,
            "cell_id": self.cell_id,
            "arfcn": self.arfcn,
            "band": self.band,
            "bandwidth": self.bandwidth,
            "plmn": self.plmn,
            "operator_name": self.operator_name,
            "connection_state": self.connection_state,

            # full raw dict from the modem
            # "raw": self.raw
        }
