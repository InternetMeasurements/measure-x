# Classe che rappresenta la funzionalità di decodifica ed esecuzione dei vari moduli sulle porbes

class CommandsMultiplexer():
    def __init__(self):
        self.commands_handler_list = {}

    
    def add_command_handler(self, interested_command, handler):
        if interested_command not in self.commands_handler_list:
            self.commands_handler_list[interested_command] = handler
            print(f"Registered handler for -> {interested_command}")
        else:
            print(f"There is already a registered handler for -> {interested_command}")

    def decode_command(self, complete_command : str):
        print(f"command_multiplexer: complete_command -> {complete_command} ")
        command_key = complete_command.split(':')[0]
        command_value = complete_command.split(':')[1].replace(' ', '')
        if command_key in self.commands_handler_list:
            self.commands_handler_list[command_key](command_value)
        else:
            print(f"Multiplexer: no registered handler for {command_key}")
        
        """CODICE VECCHIO
        L'intero math viene implementato dall'invocazione parametrica di commands_handler_list[command_key](command_value)
        match command_key:
            case "conf_iperf":
                self.iperfController.read_configuration(role = command_value)
                print(f"iperf config -> {command_value}")
            case "run_iperf":
                print(f"comando -> run_iperf")
                self.iperfController.run_iperf_repetitions()
            case _:
                print("Non conosciuto")

        """