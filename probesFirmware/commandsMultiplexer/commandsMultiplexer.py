# Classe che rappresenta la funzionalità di decodifica ed esecuzione dei vari moduli sulle porbes
import json

class CommandsMultiplexer():
    def __init__(self):
        self.commands_handler_list = {}
        #self.status_handler_list = {} # For the future. Is necessary that the probe knows about the Coordinator state? Or another probe state?

    # +------------------ commands_handler_list ------------------+
    # |      COMMAND     |          HANDLER FUNCTION              |
    # +------------------+----------------------------------------+
    # |       iperf      |  iperfController.iperf_command_handler |
    # |       ping       |                                        |
    # |   bg_generator   |                                        |
    # +------------------+----------------------------------------+

    def registration_handler_request(self, interested_command, handler) -> str:
        if interested_command not in self.commands_handler_list:
            self.commands_handler_list[interested_command] = handler
            return "OK"
        else:
            return "There is already a registered handler for " + interested_command

    def decode_command(self, complete_command):
        nested_command = json.loads(complete_command)
        # Il Decode command deve interpretare il JSON
        print(f"command_multiplexer: complete_command -> {nested_command} ")
        handler = nested_command["handler"]
        command = nested_command["command"]
        payload = nested_command["payload"]
        if handler in self.commands_handler_list:
            self.commands_handler_list[handler](command, payload)
        else:
            print(f"CommandsMultiplexer: no registered handler for {handler}")