#!/usr/bin/env python3
import os
import sys
import threading

import connexion
from modules.restAPIModule.swagger_server import encoder

current_directory = os.getcwd()
sys.path.append(os.path.join(current_directory, 'modules', 'restAPIModule'))

class RestServer:
    def __init__(self):
        self.app = connexion.App(__name__, specification_dir='./swagger/')
        self.app.app.json_encoder = encoder.JSONEncoder
        self.app.add_api('swagger.yaml', arguments={'title': 'MeasureX RestAPI'}, pythonic_params=True)
        self.server_thread = None

    def body_thread(self):
        self.app.run(port=8080)

    def start_REST_API_server(self):
        self.server_thread = threading.Thread(target = self.body_thread)
        self.server_thread.daemon = True  # Questo permette di terminare il thread quando il programma principale termina
        self.server_thread.start()