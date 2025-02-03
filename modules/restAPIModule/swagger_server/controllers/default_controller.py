import connexion
import six
from flask import current_app, Flask, jsonify
from modules.restAPIModule.swagger_server.rest_server import KEY_FOR_RETRIEVE_MONGO_INSTANCE
from modules.restAPIModule.swagger_server.rest_server import KEY_FOR_RETIREVE_COMMANDS_MULTIPLEXER
from modules.mongoModule.mongoDB import MongoDB
from modules.commandsMultiplexer.commands_multiplexer import CommandsMultiplexer

from modules.mongoModule.models.error_model import ErrorModel  # noqa: E501
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo  # noqa: E501

from swagger_server.models.inline_response200 import InlineResponse200  # noqa: E501
from swagger_server.models.inline_response2001 import InlineResponse2001  # noqa: E501
from swagger_server.models.inline_response2002 import InlineResponse2002  # noqa: E501
from swagger_server import util
from bson import ObjectId
import json

# Funzione per serializzare ObjectId
def json_serial(obj):
    if isinstance(obj, ObjectId):
        return str(obj)  # Converte l'ObjectId in stringa
    raise TypeError("Type not serializable")


def create_measurement(body):  # noqa: E501
    """Create a new measurement.

    With this enpoint, you can create a the measurement in the payload. Beware of required measurement fields.  Returns an error if required fields are missing. # noqa: E501

    :param body: 
    :type body: dict | bytes

    :rtype: MeasurementModelMongo
    """
    if connexion.request.is_json:
        try:
            measurement = MeasurementModelMongo.cast_dict_in_MeasurementModelMongo(connexion.request.get_json())  # noqa: E501
            commands_multiplexer : CommandsMultiplexer = current_app.config.get(KEY_FOR_RETIREVE_COMMANDS_MULTIPLEXER)
            msg_to_return = commands_multiplexer.prepare_probes_to_measure(measurement)
            if msg_to_return == "OK":
                return "OK", 200
            else:
                error_msg_to_return = ErrorModel(object_ref_id='', object_ref_type="measurement", error_description=msg_to_return).to_dict()
                return error_msg_to_return, 400
            # Recupera le istanze del modulo che vuoi usare, e agisci di conseguenza
            
        except Exception as e:
            json_msg = connexion.request.get_json()
            measurement_id = json_msg['measurement_id'] if 'measurement_id' in  json_msg else None
            if measurement_id is None:
                error_msg_to_return = ErrorModel(object_ref_id='No id', object_ref_type="measurement", error_description="No ")
                return error_msg_to_return, 400


def get_measurement_by_id(measurement_id):  # noqa: E501
    """Retrieve a specific measurement by ID.

    Returns the JSON object representing the measurement with the specified ID.  If the ID does not exist, a 500 error is returned. # noqa: E501

    :param measurement_id: The parameter measurement_id is the ID of the measurement to retrieve from mongoDB server.
    :type measurement_id: int

    :rtype: MeasurementModelMongo
    """

    mongo_instance : MongoDB = current_app.config.get(KEY_FOR_RETRIEVE_MONGO_INSTANCE)
    measurement_readed = mongo_instance.find_measurement_by_id(measurement_id=measurement_id)
    if isinstance(measurement_readed, ErrorModel): #"error_cause" in measurement_readed:
        return measurement_readed, 500 # Meglio indicare come codice di errore, il 400
    return measurement_readed, 200


def get_measurement_results_by_measurement_id(measurement_id):  # noqa: E501
    """Retrieve all the measurement results

    Returns the list of JSON objects representing the results related to the specified measurement.  If the specified measurement does not have any results, it will be returned an empty list. Otherwise, if the specified ID does not exist or is not valid, an error will be returned. # noqa: E501

    :param measurement_id: The parameter measurement_id is the ID of the measurement to retrieve its results, if any, from mongoDB server.
    :type measurement_id: str

    :rtype: List[Object]
    """
    print("get_measurement_results_by_measurement_id()")
    return 'do some magic!'


def get_all_measurements():  # noqa: E501
    """Retrieve all measurements.

    Returns a list of all measurements in the database. # noqa: E501


    :rtype: List[MeasurementModelMongo]
    """
    return 'do some magic!'


def get_all_results():  # noqa: E501
    """Retrieve all results.

    Returns a list of all results in the database. # noqa: E501


    :rtype: List[Object]
    """
    return 'do some magic!'


def get_measurex_general_info():  # noqa: E501
    """Get MeasureX system info

    This endpoint returns info about the MeasureX tool. # noqa: E501


    :rtype: InlineResponse200
    """
    return 'do some magic!'


def get_result_by_measurement_id(measurement_id):  # noqa: E501
    """Retrieve all the results related to measurement with specific ID.

    Returns the list of JSON object representing all the results related to that measurement.  If the ID does not exist, or is not valid one, a 500 error is returned. # noqa: E501

    :param measurement_id: The measuremnt_id of which you want the results.
    :type measurement_id: str

    :rtype: List[Object]
    """
    mongo_instance : MongoDB = current_app.config.get(KEY_FOR_RETRIEVE_MONGO_INSTANCE)
    
    result_list_as_dic = mongo_instance.find_all_results_by_measurement_id(measurement_id = measurement_id)
    if isinstance(result_list_as_dic, ErrorModel): #"error_cause" in measurement_readed:
        return result_list_as_dic, 500
    return jsonify(results=json.loads(json.dumps(result_list_as_dic, default=json_serial))), 200


def stop_measurement_by_id(measurement_id):  # noqa: E501
    """Stop a measurement by ID.

    Stops an active measurement with the given ID. Returns an error if the measurement does not exist or is already stopped. # noqa: E501

    :param measurement_id: The ID of the measurement to stop.
    :type measurement_id: int

    :rtype: None
    """
    return 'do some magic!'
