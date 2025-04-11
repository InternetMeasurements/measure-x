# coding: utf-8

from __future__ import absolute_import

from flask import json
from six import BytesIO

from swagger_server.models.error_model import ErrorModel  # noqa: E501
from swagger_server.models.inline_response200 import InlineResponse200  # noqa: E501
from swagger_server.models.inline_response2001 import InlineResponse2001  # noqa: E501
from swagger_server.models.inline_response2002 import InlineResponse2002  # noqa: E501
from swagger_server.models.measurement_model_mongo import MeasurementModelMongo  # noqa: E501
from swagger_server.test import BaseTestCase


class TestDefaultController(BaseTestCase):
    """DefaultController integration test stubs"""

    def test_create_measurement(self):
        """Test case for create_measurement

        Create a new measurement.
        """
        body = MeasurementModelMongo()
        response = self.client.open(
            '/FRANCESCO0297/measureXAPI/1.0.0/measurements',
            method='POST',
            data=json.dumps(body),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_all_measurements(self):
        """Test case for get_all_measurements

        Retrieve all measurements.
        """
        response = self.client.open(
            '/FRANCESCO0297/measureXAPI/1.0.0/measurements',
            method='GET')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_all_results(self):
        """Test case for get_all_results

        Retrieve all results.
        """
        response = self.client.open(
            '/FRANCESCO0297/measureXAPI/1.0.0/results',
            method='GET')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_measurement_by_id(self):
        """Test case for get_measurement_by_id

        Retrieve a specific measurement by ID.
        """
        response = self.client.open(
            '/FRANCESCO0297/measureXAPI/1.0.0/measurements/{measurement_id}'.format(measurement_id=56),
            method='GET')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_measurex_general_info(self):
        """Test case for get_measurex_general_info

        Get MeasureX system info
        """
        response = self.client.open(
            '/FRANCESCO0297/measureXAPI/1.0.0/measureX',
            method='GET')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_result_by_id(self):
        """Test case for get_result_by_id

        Retrieve a specific result by ID.
        """
        response = self.client.open(
            '/FRANCESCO0297/measureXAPI/1.0.0/results/{result_id}'.format(result_id=56),
            method='GET')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_stop_measurement_by_id(self):
        """Test case for stop_measurement_by_id

        Stop a measurement by ID.
        """
        response = self.client.open(
            '/FRANCESCO0297/measureXAPI/1.0.0/measurements/{measurement_id}'.format(measurement_id=56),
            method='DELETE')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))


if __name__ == '__main__':
    import unittest
    unittest.main()
