# Classe che rappresenta la funzionalità di decodifica ed esecuzione dei vari moduli sulle porbes

class CommandsMultiplexer():
    def __init__(self):
        self.commands_handler_list = {}

    # +------------------ commands_handler_list ------------------+
    # |      COMMAND     |          HANDLER FUNCTION              |
    # +------------------+----------------------------------------+
    # |       iperf      |  iperfController.iperf_command_handler |
    # |       ping       |                                        |
    # |   bg_generaror   |                                        |
    # +------------------+----------------------------------------+

    def registration_handler_request(self, interested_command, handler) -> str:
        if interested_command not in self.commands_handler_list:
            self.commands_handler_list[interested_command] = handler
            return "OK"
        else:
            return "There is already a registered handler for -> " + interested_command

    def decode_command(self, complete_command : str):
        print(f"command_multiplexer: complete_command -> {complete_command} ")
        command_key = complete_command.split(':')[0]
        command_value = complete_command.split(':')[1].replace(' ', '')
        if command_key in self.commands_handler_list:
            self.commands_handler_list[command_key](command_value)
        else:
            print(f"CommandsMultiplexer: no registered handler for {command_key}")