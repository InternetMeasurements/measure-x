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

A Measure-X installation comprises the following elements: 
 - a coordinator: it's the Measure-X component that coordinates the probes and receives measurement specifications from the user
 - a number of probes: every probe is a measuring endpoint; probes are Raspberry PI5 devices equipped with a 5G module
 - an MQTT broker: it is used to make the coordinator and the probes communicate with each other. 
 
[INSTALLATION](./ISTALLATION.md)

[EXAMPLES](./EXAMPLES.md)



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

On probes, the software can be downloaded using the following command: 
```
gh repo clone InternetMeasurements/measure-x
```

The probes's Measure-X software can be started with 
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

## Configuration of Ansible
Ansible makes possible to configure probes without manual installing all the required software. 
The Ansible hosts file 
```
/etc/ansible/hosts
```
must be configure in this way:
```
[probes] # Name Group
 probe1 ansible_ssh_host=192.168.43.211
  ansible_user=probe1
  ansible_ssh_private_key_file=/home/francesco/pub_keys/probe1
 probe2 ansible_ssh_host=192.168.43.210
  ansible_user=probe2
  ansible_ssh_private_key_file=/home/francesco/pub_keys/probe2
 probe3 ansible_ssh_host=192.168.43.131
  ansible_user=probe3
  ansible_ssh_private_key_file=/home/francesco/pub_keys/probe3
 probe4 ansible_ssh_host=192.168.43.152
  ansible_user=probe4
  ansible_ssh_private_key_file=/home/francesco/pub_keys/probe4
 probe5 ansible_ssh_host=192.168.43.254
  ansible_user=probe5
  ansible_ssh_private_key_file=/home/francesco/pub_keys/probe5
```
change the above paths so that they point to the ssh keys to be used for authentication onto the different probes. Similarly, change the IP addresses so that they correspond to the ones of the probes.

This ansible playbook 
```
probes_initialization.yaml
```
that is available in the repository can be used to configure the probes. 

The playbook can then be executed as follows: 
```
ansible-playbook probes initialization.yaml
```

## Preparing the RM520N-GL modem
The RM520N-GL 5G modem requires an initial configuration before its first use. This guide
https://download.kamami.pl/p1185265-Quectel_RG520N%26RG52xF%26RG530F%26RM520N%26RM530N_Series_AT_Commands_Manual_V1.0.0_Preliminary_20220812.pdf
explains how to enable the 5G modem to communicate through the serial port in
addition to PCIe. For troubleshooting scenarios where the modem does not operate
correctly, accessing it via the serial interface and using AT commands has proven to be highly convenient.  To interact through the serial connection, the modem is exposed as a device under `/dev/mhi DUN`. Using the minicom tool, it is possible to establish a direct connection with the modem and communicate via supported AT commands, as specified in the official manual.