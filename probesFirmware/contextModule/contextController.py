import serial
import time
from datetime import datetime


class ContextController:

    def __init__(self, port="/dev/mhi_DUN", baudrate=115200, timeout=1.5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = serial.Serial(port=self.port, baudrate=self.baudrate, timeout=self.timeout)


    def send_at(self, cmd, timeout=2.0):
        """
        Send an AT command and return all lines until OK/ERROR.
        """
        try:
            full_cmd = (cmd + "\r").encode()
            self.serial.reset_input_buffer()
            self.serial.write(full_cmd)

            end_time = time.time() + timeout
            lines = []

            while time.time() < end_time:
                line = self.serial.readline().decode(errors="ignore").strip()
                if line:
                    lines.append(line)
                    if line == "OK" or line.startswith("ERROR"):
                        break

            return "\n".join(lines)

        except Exception as e:
            print(f"ContextModule ERROR sending AT '{cmd}': {e}")
            return ""


    def extract(self, raw, prefix):
        for l in raw.splitlines():
            if l.strip().startswith(prefix):
                return l.strip()
        return None


    def parse_qeng_servingcell(self, raw):
        lines = [l.strip() for l in raw.splitlines() if l.strip().startswith("+QENG:")]

        if len(lines) == 0:
            return {}

        if any('"NR5G-NSA"' in l for l in lines) and any('"LTE"' in l for l in lines):

            lte_line = next(l for l in lines if '"LTE"' in l)
            nr_line = next(l for l in lines if '"NR5G-NSA"' in l)

            l = lte_line.split(",")
            n = nr_line.split(",")
            try:
                return {
                    "rat": "NR5G",
                    "mode": "NSA",
                    # LTE part
                    "cell_id": l[4],
                    # NR
                    "plmn": n[1] + n[2],
                    "pci": int(n[3]),
                    "rsrp": int(n[4]),
                    "sinr": int(n[5]),
                    "rsrq": int(n[6]),
                    "arfcn": int(n[7]),
                    "band": n[8],
                    "bandwidth": n[9],
                    "cqi": None,
                    "tac": None
                }
            except Exception:
                #Debug
                #print("Eccezione")
                return {}

        if any('"NR5G-SA"' in l for l in lines):

            line = next(l for l in lines if '"NR5G-SA"' in l)
            p = line.split(",")

            try:
                return {
                    "rat": "NR5G",
                    "mode": "SA",
                    "plmn": p[4] + p[5],
                    "cell_id": int(p[6]),
                    "pci": int(p[7]),
                    "tac": int(p[8]),
                    "arfcn": int(p[9]),
                    "band": p[10],
                    "bandwidth": p[11],
                    "rsrp": int(p[12]),
                    "rsrq": int(p[13]),
                    "sinr": int(p[14]),
                    "cqi": None,
                }
            except Exception:
                #Debug
                #print("Eccezione")
                return {}

        if any('"LTE"' in l for l in lines):

            line = next(l for l in lines if '"LTE"' in l)
            p = line.split(",")

            try:
                return {
                    "rat": "LTE",
                    "mode": p[3].replace('"', ''),
                    "plmn": p[4] + p[5],
                    "cell_id": int(p[6]),
                    "pci": int(p[7]),
                    "arfcn": int(p[8]),
                    "band": p[9],
                    "bandwidth": p[11],
                    "tac": int(p[12]),
                    "rsrp": int(p[13]),
                    "rsrq": int(p[14]),
                    "sinr": int(p[16]),
                    "cqi": int(p[17])
                }
            except Exception:
                #Debug
                #print("Eccezione")
                return {}
        
        if any('"WCDMA"' in l for l in lines):

            line = next(l for l in lines if '"WCDMA"' in l)
            p = line.split(",")

            try:
                return {
                    "rat": "WCDMA",
                    "mode": None,
                    "plmn": p[3] + p[4],
                    "cell_id": int(p[6]),
                    "pci": int(p[8]),
                    "arfcn": int(p[7]),
                    "band": None,
                    "bandwidth": None,
                    "tac": int(p[5]),
                    "rsrp": int(p[10]),
                    "rsrq": int(p[11]),
                    "sinr": None,
                    "cqi": None
                }
            except Exception:
                #Debug
                #print("Eccezione")
                return {}


    def parse_qnwinfo(self, raw):
        line = self.extract(raw, "+QNWINFO:")
        if not line:
            return {}

        try:
            items = line.split(":", 1)[1].split(",")
            return {
                "band": items[2].replace('"', '').strip(),
            }
        except Exception:
            return {}


    def parse_cops(self, raw):
        line = self.extract(raw, "+COPS:")
        if not line:
            return {}

        try:
            fields = line.split(",")
            return {"operator_name": fields[2].replace('"', "")}
        except Exception:
            return {}


    def parse_csq(self, raw):
        line = self.extract(raw, "+CSQ:")
        if not line:
            return {}

        try:
            rssi = int(line.split(":")[1].split(",")[0])
            ber = int(line.split(":")[1].split(",")[1])
            return {
                "rssi": 99 if rssi == 99 else rssi * 2 - 113,
                "ber": ber
                }
        except Exception:
            return {}


    def parse_creg(self, raw):
        if "+CREG:" not in raw:
            return {}

        try:
            state = raw.split(",")[-1].strip()
            return {"connection_state": state}
        except Exception:
            return {"connection_state": None}


    def read_context(self, msm_id):
        ctx = {"msm_id": msm_id}
        
        # Serving cell
        qeng = self.send_at('AT+QENG="servingcell"')
        ctx.update(self.parse_qeng_servingcell(qeng))
        print(ctx)

        # Info operative band frequency
        qnw = self.send_at("AT+QNWINFO")
        ctx.update(self.parse_qnwinfo(qnw))

        # Operator name
        cops = self.send_at("AT+COPS?")
        ctx.update(self.parse_cops(cops))

        # RSSI fallback
        csq = self.send_at("AT+CSQ")
        ctx.update(self.parse_csq(csq))

        # Registration
        creg = self.send_at("AT+CREG?")
        ctx.update(self.parse_creg(creg))
        print(ctx) 
        
        return ctx
