# Classe che rappresenta la funzionalità di decodifica ed esecuzione dei vari moduli sulle porbes
from src.modules.probesFirmware.commandsExecutor.iperfClient.iperfController import IperfController

class CommandsExecutor():
    def __init__(self):
        self.role_topic = None
        self.command_topic = None
        self.iperfController = IperfController()
        return
    
    def set_role_and_command_topic(self, role_topic, command_topic):
        self.role_topic = role_topic
        self.command_topic = command_topic

    def decode_command(self, complete_command : str):
        print(f"decode-> complete_command: {complete_command} ")
        command_key = complete_command.split(':')[0]
        command_value = complete_command.split(':')[1]
        match command_key:
            case "role":
                print(f"ruolo -> {command_value}")
            case "conf_iperf":
                print(f"iperf config -> {command_value}")
            case "run_iperf":
                print(f"comando -> run_iperf")
                self.iperfController.run_iperf_repetitions()
            case _:
                print("Non conosciuto")