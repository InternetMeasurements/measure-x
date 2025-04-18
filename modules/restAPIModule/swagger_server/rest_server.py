#!/usr/bin/env python3
import os
import sys
import threading

import connexion
from modules.restAPIModule.swagger_server import encoder
from modules.mongoModule.mongoDB import MongoDB

current_directory = os.getcwd()
sys.path.append(os.path.join(current_directory, 'modules', 'restAPIModule'))

KEY_FOR_RETRIEVE_MONGO_INSTANCE = 'MONGO_INSTANCE'
KEY_FOR_RETIREVE_COMMANDS_MULTIPLEXER = 'COMMAND_MULTIPLEXER_INSTANCE'

class RestServer:
    def __init__(self, mongo_instance : MongoDB, commands_multiplexer_instance = None):
        self.app = connexion.App(__name__, specification_dir='./swagger/')
        self.app.app.json_encoder = encoder.JSONEncoder
        self.app.add_api('swagger.yaml', arguments={'title': 'MeasureX RestAPI'}, pythonic_params=True)
        self.app.app.config[KEY_FOR_RETRIEVE_MONGO_INSTANCE] = mongo_instance
        self.app.app.config[KEY_FOR_RETIREVE_COMMANDS_MULTIPLEXER] = commands_multiplexer_instance
        self.server_thread = None

    def body_thread(self):
        self.app.run(port=8085)

    def start_REST_API_server(self):
        self.server_thread = threading.Thread(target = self.body_thread)
        self.server_thread.daemon = True  # Questo permette di terminare il thread quando il programma principale termina
        self.server_thread.start()