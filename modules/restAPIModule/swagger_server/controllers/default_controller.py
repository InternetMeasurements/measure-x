import connexion
import six

from modules.mongoModule.models.error_model import ErrorModel  # noqa: E501
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo  # noqa: E501

from swagger_server.models.inline_response200 import InlineResponse200  # noqa: E501
from swagger_server.models.inline_response2001 import InlineResponse2001  # noqa: E501
from swagger_server.models.inline_response2002 import InlineResponse2002  # noqa: E501
from swagger_server import util


def create_measurement(body):  # noqa: E501
    """Create a new measurement.

    With this enpoint, you can create a the measurement in the payload.   Beware of required measurement fields.  Returns an error if required fields are missing. # noqa: E501

    :param body: 
    :type body: dict | bytes

    :rtype: MeasurementModelMongo
    """
    if connexion.request.is_json:
        body = MeasurementModelMongo.from_dict(connexion.request.get_json())  # noqa: E501
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


    :rtype: List[InlineResponse2002]
    """
    return 'do some magic!'


def get_measurement_by_id(measurement_id):  # noqa: E501
    """Retrieve a specific measurement by ID.

    Returns the JSON object representing the measurement with the specified ID.  If the ID does not exist, a 500 error is returned. # noqa: E501

    :param measurement_id: The parameter measurement_id is the ID of the measurement to retrieve from mongoDB server.
    :type measurement_id: int

    :rtype: MeasurementModelMongo
    """
    return 'do some magic!'


def get_measurex_general_info():  # noqa: E501
    """Get MeasureX system info

    This endpoint returns info about the MeasureX tool. # noqa: E501


    :rtype: InlineResponse200
    """
    return 'do some magic!'


def get_result_by_id(result_id):  # noqa: E501
    """Retrieve a specific result by ID.

    Returns the JSON object representing the result with the specified ID.  If the ID does not exist, a 500 error is returned. # noqa: E501

    :param result_id: The ID of the result to retrieve.
    :type result_id: int

    :rtype: InlineResponse2001
    """
    return 'do some magic!'


def stop_measurement_by_id(measurement_id):  # noqa: E501
    """Stop a measurement by ID.

    Stops an active measurement with the given ID. Returns an error if the measurement does not exist or is already stopped. # noqa: E501

    :param measurement_id: The ID of the measurement to stop.
    :type measurement_id: int

    :rtype: None
    """
    return 'do some magic!'
