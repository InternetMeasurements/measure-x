import smbus
import time
import subprocess
from gpiozero import PIN
import csv
import threading

SYNC_OTII_PIN = 4
DEFAULT_CURRENT_MEASUREMENT_FILE = "ina219_measurements.csv"

class Ina219Driver:
    def __init__(self, current_compare : bool = False):
        #self.chip = gpiod.Chip('gpiochip4')
        #self.otii_sync_pin = self.chip.get_line(SYNC_OTII_PIN)
        #self.otii_sync_pin.request(consumer='LED', type=gpiod.LINE_REQ_DIR_OUT)
        self.otii_sync_pin = PIN(SYNC_OTII_PIN)
        self.otii_sync_pin.off()
        self.ina219 = INA219(addr=0x40)
        self.stop_thread_event = threading.Event()
        self.measurement_thread = None
        self.last_filename = None
        self.current_compare = current_compare

        #if not self.ina219.is_device_present():
            #raise Exception("INA219 NOT FOUND ON i2C BUS")

    def start_current_measurement(self, filename = None) -> str:
        try:
            self.last_filename = DEFAULT_CURRENT_MEASUREMENT_FILE if filename is None else filename
            self.measurement_thread = threading.Thread(target=self.body_measurement_thread, args=())
            self.measurement_thread.start()
            return "OK"
        except Exception as e:
            return str(e)

    def stop_current_measurement(self) -> str:
        if self.measurement_thread != None:
            self.stop_thread_event.set()
            self.measurement_thread.join()
            return "OK"
        self.measurement_thread = None
        return "No current measurement started"

    def body_measurement_thread(self):
        with open(self.last_filename, mode="w", newline="") as csv_file:
            fieldnames = ["Timestamp", "Current"]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            try:
                if self.current_compare:
                    print(f"[CURRENT_COMPARE] SYNC GPIO{SYNC_OTII_PIN} HIGH")
                #self.otii_sync_pin.set_value(1)
                self.otii_sync_pin.on()
                while not self.stop_thread_event.is_set():
                    #GPIO.output(otii_sync_pin, not GPIO.input(otii_sync_pin))
                    current = self.ina219.getCurrent_mA() / 1000

                    timestamp = time.time()
                    writer.writerow({"Timestamp": timestamp, "Current": current})

                    #print(f"Timestamp: {timestamp}, Current: {current} A")

                    time.sleep(0.034)  # tempo di sleep per 32 campioni a 12 bit

            except KeyboardInterrupt:
                print("Measurement stopped from keyboard")
            finally:
                #self.otii_sync_pin.set_value(0)
                self.otii_sync_pin.off()
                if self.current_compare:
                    print(f"[CURRENT_COMPARE] SYNC GPIO{SYNC_OTII_PIN} LOW")
                csv_file.close()
                #self.otii_sync_pin.release()
                #self.chip.close()
        
# --------------------------------- CLASS INA219 - LOW LEVEL ---------------------------------

# Config Register (R/W)
_REG_CONFIG = 0x00
# SHUNT VOLTAGE REGISTER (R)
# _REG_SHUNTVOLTAGE = 0x01 -- NOT USED
# BUS VOLTAGE REGISTER (R)
# _REG_BUSVOLTAGE = 0x02 -- NOT USED
# POWER REGISTER (R)
# _REG_POWER = 0x03 -- NOT USED
# CURRENT REGISTER (R)
_REG_CURRENT = 0x04
# CALIBRATION REGISTER (R/W)
_REG_CALIBRATION = 0x05

class BusVoltageRange:
    """Constants for ``bus_voltage_range``"""
    RANGE_16V = 0x00  # set bus voltage range to 16V
    RANGE_32V = 0x01  # set bus voltage range to 32V (default)

class Gain:
    """Constants for ``gain``"""
    DIV_1_40MV = 0x00  # shunt prog. gain set to 1, 40 mV range
    DIV_2_80MV = 0x01  # shunt prog. gain set to /2, 80 mV range
    DIV_4_160MV = 0x02  # shunt prog. gain set to /4, 160 mV range
    DIV_8_320MV = 0x03  # shunt prog. gain set to /8, 320 mV range

class ADCResolution:
    """Constants for ``bus_adc_resolution`` or ``shunt_adc_resolution``"""
    ADCRES_9BIT_1S          = 0x00      #  9bit,   1 sample,     84us
    ADCRES_10BIT_1S         = 0x01      # 10bit,   1 sample,    148us
    ADCRES_11BIT_1S         = 0x02      # 11 bit,  1 sample,    276us
    ADCRES_12BIT_1S         = 0x03      # 12 bit,  1 sample,    532us
    ADCRES_12BIT_2S         = 0x09      # 12 bit,  2 samples,  1.06ms
    ADCRES_12BIT_4S         = 0x0A      # 12 bit,  4 samples,  2.13ms
    ADCRES_12BIT_8S         = 0x0B      # 12bit,   8 samples,  4.26ms
    ADCRES_12BIT_16S        = 0x0C      # 12bit,  16 samples,  8.51ms
    ADCRES_12BIT_32S        = 0x0D      # 12bit,  32 samples, 17.02ms
    ADCRES_12BIT_64S        = 0x0E      # 12bit,  64 samples, 34.05ms
    ADCRES_12BIT_128S       = 0x0F      # 12bit, 128 samples, 68.10ms

class Mode:
    """Constants for ``mode``"""
    POWERDOW                = 0x00      # power down
    SVOLT_TRIGGERED         = 0x01      # shunt voltage triggered
    BVOLT_TRIGGERED         = 0x02      # bus voltage triggered
    SANDBVOLT_TRIGGERED     = 0x03      # shunt and bus voltage triggered
    ADCOFF                  = 0x04      # ADC off
    SVOLT_CONTINUOUS        = 0x05      # shunt voltage continuous
    BVOLT_CONTINUOUS        = 0x06      # bus voltage continuous
    SANDBVOLT_CONTINUOUS    = 0x07      # shunt and bus voltage continuous

class INA219:
    def __init__(self, i2c_bus=1, addr=0x40):
        self.bus = smbus.SMBus(i2c_bus)
        self.addr = addr
        self._current_lsb = 0
        self._power_lsb = 0
        self._cal_value = 0
        self.set_calibration_16V_8A()

    def is_device_present(self):
        try:
            self.bus.write_quick(self.addr)
            return True
        except OSError:
            return False

    def read(self, address):
        data = self.bus.read_i2c_block_data(self.addr, address, 2)
        return ((data[0] << 8) | data[1])

    def write(self, address, data):
        self.bus.write_i2c_block_data(self.addr, address, [(data >> 8) & 0xFF, data & 0xFF])

    def set_calibration_16V_8A(self):
        """Configure INA219 to measure up to 16V and 8A.
        WARNING --> Does not change the values:
        All the values here, has been calculated with Datasheet."""
        self._current_lsb = 0.00025
        self._power_lsb = self._current_lsb * 20
        self._cal_value = 16384

        self.write(_REG_CALIBRATION, self._cal_value)

        self.bus_voltage_range = BusVoltageRange.RANGE_16V
        self.gain = Gain.DIV_2_80MV
        self.bus_adc_resolution = ADCResolution.ADCRES_12BIT_32S
        self.shunt_adc_resolution = ADCResolution.ADCRES_12BIT_32S
        self.mode = Mode.SANDBVOLT_CONTINUOUS
        self.config = (
            self.bus_voltage_range << 13
            | self.gain << 11
            | self.bus_adc_resolution << 7
            | self.shunt_adc_resolution << 3
            | self.mode
        )
        self.write(_REG_CONFIG, self.config)

    def getCurrent_mA(self):
        value = self.read(_REG_CURRENT)
        if value > 32767:
            value -= 65535
        return value * self._current_lsb * 1000  # Convert to mA

"""
    def getShuntVoltage_mV(self):
        value = self.read(_REG_SHUNTVOLTAGE)
        if value > 32767:
            value -= 65535
        return value * 0.01

    def getBusVoltage_V(self):
        value = self.read(_REG_BUSVOLTAGE)
        return (value >> 3) * 0.004


    def getPower_W(self):
        value = self.read(_REG_POWER)
        if value > 32767:
            value -= 65535
        return value * self._power_lsb
"""

"""
    Using the ADCRES_12BIT_32S setting means that the INA takes 32 samples and returns the average. 
    To perform this calculation, the maximum reading frequency is just over 50Hz, which is a bit 
    low when compared to the power monitor.
    So, if the sample frequency precision is not sufficient, I can use ADCRES_12BIT_4S, meaning 
    instead of 32, only 4 values are sampled, their average is calculated, and returned. 
    This way, since it’s 8 times fewer samples, it allows a reading frequency 8 times higher 
    than the previous setting, i.e., 460Hz.
    *** WARNING: ***
    Remember to change both the ADCRES_12BIT_4S and the sleep period to about (0.00217), considering a frequency of 460Hz.
"""