# Measure-X

Measure-X is a tool for collecting performance metrics in a 5G network. 
Probes are coordinated to collect the following metrics: 
 - latency
 - throughput
 - age of information
 - energy

While some probes collect the metrics of interest, other probes can, at the same time, generate background traffic. 
The goal is to understand the impact of coexisting applications in terms of network metrics.

In its current implementation, probes are Raspberry PI single-board computers equipped with a 5G module. 


## Installing the coordinator 

First, download the Measure-X code from the repository:
```
gh repo clone InternetMeasurements/measure-x
```
Create a virtual Python environment and activate it:
```
python3 -m venv venv
source venv/bin/activate
```
Install all the required packages:
```
python3 -m pip install -r measure-x/requirements.txt
````

Install MongoDB locally. For MacOS, you can use the following commands:
```
brew tap mongodb/brew
brew update
brew install mongodb-community@8.0
````

You can then start and stop MongoDB using the following commands:
```
brew services start mongodb-community@8.0
brew services stop mongodb-community@8.0
````

Create a measurex user:
```
mongosh admin --eval "db.createUser({
    user: 'measurex',
    pwd: 'MEASUREX_MONGODB_PASSWORD',
    roles: [{ role: 'readWrite', db: 'measurexDB' }]
})"
```
The coordinator can be started using the following command:
```
python3 measure-x/coordinator.py
```

The coordinator can also be executed on a Raspberry PI. In that case, you can use the ansible file to automate the installation operations. 



## Probes

This is the set of steps to be carried out for installing Measure-X on probes:
- git-pull of Measure-X: Download Measure-X software from GitHub
- create measurex venv: Creation of a virtual Python environment to avoid
interfering with any existing Python installation.
- dependences installing: Installation of all dependencies defined in the file
MeasureX/probesFirmware/requirements.txt
- iperf3 installing: Installation of the iperf3 tool for throughput measurements
- ntpsec installing: Installation of the ntpsec tool for clock synchronization used for AoI measurements in the corresponding module
- tcpreplay installing: Installation of the tcpreplay suite for the coexisting
application
- changing metric for WiFi connection: The metric for the WiFi connection
was set to 99 to prevent the system from defaulting to eth0 for all traffic. eth0 is used only for clock synchronization before an AoI measurement.

On probes, the software can ba downloaded using the following command: 
```
gh repo clone InternetMeasurements/measure-x
```

The probes's Measure-X coftware can be started with 
```
python3 probesFirmware/firmware.py
````

The --debug option of the firmware.py script can be used to test a probe using Wi-Fi instead of 5G.


## Installing the MQTT broker
We used Measure-X with the mosquitto MQTT broker. 
On Linux, the following command should be enough to install moquitto:
```
sudo apt install mosquitto
````

The mosquitto configuration file is
```
/etc/mosquitto/mosquitto.conf
````

We used port 8080 to avoid issues with possible firewalls, so in the end the mosquitto.conf file should look like this:
```
listener: 8080
cafile /etc/mosquitto/certs/mosquitto.crt
certfile /etc/mosquitto/certs/mosquitto.crt
keyfile /etc/mosquitto/certs/mosquitto.key

persistence true
persistence_location /var/lib/mosquitto/

log_dest file /var/log/mosquitto/mosquitto.log

include_dir /etc/mosquitto/conf.d

allow_anonymous false
password_file /etc/mosquitto/passwd
```
After configuration, mosquitto should be restarted:
```
sudo systemctl restart mosquitto
```