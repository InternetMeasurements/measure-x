"""
mongoDB.py

This module provides the MongoDB class for managing measurement and result data in a MongoDB database for the Measure-X system. It supports inserting, updating, deleting, and querying measurements and results, as well as plotting and analysis utilities for time series data.
"""

import time, json, os
from pathlib import Path
from bson import ObjectId
from datetime import datetime
from pymongo import MongoClient
from modules.mongoModule.models.error_model import ErrorModel
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
"""
from modules.mongoModule.models.ping_result_model_mongo import PingResultModelMongo
from modules.mongoModule.models.iperf_result_model_mongo import IperfResultModelMongo
from modules.mongoModule.models.energy_result_model_mongo import EnergyResultModelMongo
from modules.mongoModule.models.coex_result_model_mongo import CoexResultModelMongo
"""


HOURS_OLD_MEASUREMENT = 24
SECONDS_OLD_MEASUREMENT = HOURS_OLD_MEASUREMENT * 3600
STARTED_STATE = "started"
FAILED_STATE = "failed"
COMPLETED_STATE = "completed"


class MongoDB:
    """
    MongoDB interface for storing, updating, and retrieving measurement and result data.
    Provides methods for managing measurement lifecycle, linking results, and plotting/analysis utilities.
    """

    def __init__(self, mongo_config):
        """
        Initialize the MongoDB connection and collections.
        Args:
            mongo_config: Configuration object with MongoDB connection parameters.
        """
        self.server_ip = mongo_config.ip_server
        self.server_port = mongo_config.port_server
        self.user = mongo_config.user
        self.password = mongo_config.password
        self.db_name = mongo_config.db_name
        self.measurements_collection_name = mongo_config.measurements_collection_name
        self.results_collection_name = mongo_config.results_collection_name
        self.client = MongoClient("mongodb://" + self.user + ":" + self.password + "@" + self.server_ip + ":" + str(self.server_port) + "/")
        self.measurements_collection = None
        self.results_collection = None

        db = self.client[self.db_name] # crea il db measurex

        if self.measurements_collection_name not in db.list_collection_names(): # if the measurements_collection doesn't exists, then creates it
            db.create_collection(self.measurements_collection_name)

        if self.results_collection_name not in db.list_collection_names():  # if the results_collection doesn't exists, then creates it
            db.create_collection(self.results_collection_name)
        
        self.measurements_collection = db[self.measurements_collection_name]
        self.results_collection = db[self.results_collection_name]

    # ------------------------------------------------- MEASUREMENTS COLLECTION -------------------------------------------------
    
    def insert_measurement(self, measure : MeasurementModelMongo) -> str:
        """
        Insert a new measurement document into the measurements collection.
        Args:
            measure (MeasurementModelMongo): The measurement to insert.
        Returns:
            str: The inserted measurement's ID, or None on failure.
        """
        try:
            measure.start_time = time.time()
            measure.state = STARTED_STATE
            insert_result = self.measurements_collection.insert_one(measure.to_dict(True))
            if insert_result.inserted_id:
                print(f"MongoDB: measurement stored in mongo. ID -> |{insert_result.inserted_id}|")
                return insert_result.inserted_id
        except Exception as e:
            print(f"MongoDB: Error while storing the measurment on mongo -> {e}")
            return None
        
    def replace_measurement(self, measurement_id, measure : MeasurementModelMongo):
        """
        Replace an existing measurement document by ID.
        Args:
            measurement_id (str): The ID of the measurement to replace.
            measure (MeasurementModelMongo): The new measurement data.
        Returns:
            bool: True if replaced, False otherwise.
        """
        result = self.measurements_collection.replace_one({"_id": ObjectId(measurement_id)}, measure.to_dict(to_store = True))
        return (result.matched_count > 0)

    def set_measurement_as_completed(self, measurement_id) -> bool:
        """
        Mark a measurement as completed and set its stop time.
        Args:
            measurement_id (str): The ID of the measurement to update.
        Returns:
            bool: True if updated, False otherwise.
        """
        stop_time = time.time()
        update_result = self.measurements_collection.update_one(
                            {"_id": ObjectId(measurement_id)},
                            {"$set": {"stop_time": stop_time,
                                      "state": COMPLETED_STATE} })
        return (update_result.modified_count > 0)


    def set_measurement_as_failed_by_id(self, measurement_id : str) -> bool:
        """
        Mark a measurement as failed by its ID.
        Args:
            measurement_id (str): The ID of the measurement to update.
        Returns:
            bool: True if updated, False otherwise.
        """
        replace_result = self.measurements_collection.update_one(
                            {"_id": ObjectId(measurement_id)},
                            {"$set":{
                                "_id": ObjectId(measurement_id),
                                "state": FAILED_STATE
                                }
                            })
        return (replace_result.modified_count > 0)
    
    
    def update_results_array_in_measurement(self, msm_id, result_id = None):
    # This method is an automatic setting of the results doc-linking in measurements collection. 
    # It finds all the results with that msm_id, and store them _ids in the doc-link
        try:
            if result_id is None:
                update_result = self.measurements_collection.update_one(
                    {"_id": ObjectId(msm_id)},
                    {"$set": {"results": list(
                        self.results_collection.find({"msm_id": ObjectId(msm_id)}).distinct("_id"))}}
                )
            else:
                update_result = self.measurements_collection.update_one(
                    {"_id": ObjectId(msm_id)},
                    {"$set": {"results": [str(result_id)]}}
                )
            return update_result
        except Exception as e:
            print(f"Motivo -> {e}")
            find_result = ErrorModel(object_ref_id = msm_id, object_ref_type="list of results", 
                                     error_description="It must be a 12-byte input or a 24-character hex string",
                                     error_cause="measurement_id NOT VALID")
        return (find_result.to_dict())
    

    def delete_measurements_by_id(self, measurement_id: str) -> bool:
        """
        Delete a measurement document by its ID.
        Args:
            measurement_id (str): The ID of the measurement to delete.
        Returns:
            bool: True if deleted, False otherwise.
        """
        # Da cancellare
        delete_result = self.measurements_collection.delete_one(
                            {"_id": ObjectId(measurement_id)})
        return (delete_result.deleted_count > 0)


    def find_measurement_by_id(self, measurement_id):
        """
        Find a measurement by its ID and return as a MeasurementModelMongo or ErrorModel.
        Args:
            measurement_id (str): The ID of the measurement to find.
        Returns:
            MeasurementModelMongo or ErrorModel: The found measurement or error info.
        """
        try:
            find_result = self.measurements_collection.find_one({"_id": ObjectId(measurement_id)})
            if find_result is None:
                find_result = ErrorModel(object_ref_id=measurement_id, object_ref_type="measurement",
                                         error_description="Measurement not found in DB",
                                         error_cause="Unknown measurement_id")
            else:
                find_result = MeasurementModelMongo.cast_dict_in_MeasurementModelMongo(find_result)
                dt = datetime.fromtimestamp(find_result.start_time)
                find_result.start_time = dt.strftime("%H:%M:%S.%f %d/%m/%Y")
                if (find_result.state == "completed") and (find_result.stop_time is not None):
                    dt = datetime.fromtimestamp(find_result.stop_time)
                    find_result.stop_time = dt.strftime("%H:%M:%S.%f %d/%m/%Y")
        except Exception as e:
            print(f"MongoDB: exception in find_measurement_by_id -> {e}")
            find_result = ErrorModel(object_ref_id=measurement_id, object_ref_type="measurement", 
                                     error_description="It must be a 12-byte input or a 24-character hex string",
                                     error_cause="measurement_id NOT VALID")
        return find_result


    def get_measurement_state(self, measurement_id) -> str:
        """
        Get the state of a measurement by its ID.
        Args:
            measurement_id (str): The ID of the measurement.
        Returns:
            str: The state of the measurement, or None if not found.
        """
        measurement_result : MeasurementModelMongo = self.measurements_collection.find_one({"_id": ObjectId(measurement_id)})
        if measurement_result is None:
            return None
        return (measurement_result.state)
    
    
    def get_old_measurements_not_yet_setted_as_failed(self) -> list[MeasurementModelMongo]:
        """
        Get a list of old measurements (older than 24 hours) that are still marked as started.
        Returns:
            list[MeasurementModelMongo]: List of old measurements.
        """
        twenty_four_hours_ago  = time.time() - SECONDS_OLD_MEASUREMENT
        old_measurements = self.measurements_collection.find(
                            {"start_time": {"$lt": twenty_four_hours_ago},
                             "state": STARTED_STATE})
        return list(old_measurements)
    
    
    def set_old_measurements_as_failed(self) -> int:
        """
        Mark all old measurements (older than 24 hours) as failed.
        Returns:
            int: The number of measurements updated.
        """
        twenty_four_hours_ago  = time.time() - SECONDS_OLD_MEASUREMENT
        replace_result = self.measurements_collection.update_many(
                            { "start_time": {"$lt": twenty_four_hours_ago} ,
                              "state": STARTED_STATE },
                            {"$set":{
                                "state": FAILED_STATE
                                }
                            })
        return replace_result.modified_count
    
    def find_and_plot(self, msm_id, start_coex, stop_coex, series_name, time_field, value_field, granularity):
        """
        Find all results for a measurement and plot the specified time series with optional coexisting application highlighting.
        Args:
            msm_id (str): The measurement ID.
            start_coex (float): Start time of coexisting application.
            stop_coex (float): Stop time of coexisting application.
            series_name (str): The name of the series to plot.
            time_field (str): The field name for time.
            value_field (str): The field name for values.
            granularity (str): The resampling granularity (e.g., '1S').
        """
        import matplotlib.pyplot as plt
        import numpy as np

        result = self.find_all_results_by_measurement_id(msm_id=msm_id)
        aois = result[0][series_name]


        timestamps = np.array([aoi_data[time_field] for aoi_data in aois], dtype=float)
        values = np.array([aoi_data[value_field] for aoi_data in aois], dtype=float)

        timestamps -= timestamps[0]
        max_value = timestamps[-1]
        plot_name = "Energy" if value_field == "Current" else "AoI"
        plt.figure(figsize=(10, 6))

        plt.plot(timestamps, values, marker='o', linestyle='-', color='#B85450', label=value_field)
        plt.xlabel("Timestamp (s)", fontsize=16)

        ylabel = "AoI (mS)" if plot_name == "AoI" else "Current (A)"
        plt.ylabel(ylabel, fontsize=16)

        if plot_name == "AoI":
            plt.axvspan(xmin=start_coex, xmax=stop_coex, color='#82B366', alpha=0.3, label="Coexisting Application")

        plt.rcParams['font.size'] = 14
        value_max = values.max()
        plt.xticks(np.arange(0, timestamps[-1], 2), fontsize=16)
        if plot_name == "AoI":
            plt.yticks(np.arange(0, value_max, 20), fontsize=16)
        else:
            plt.yticks(np.arange(0, value_max, 10/1000), fontsize=16)


        plt.title("Measuring " + plot_name + ("" if plot_name == "Energy" else " with Coexisting Application traffic"),  fontsize=16)
        plt.grid(axis='x')
        plt.legend()
        plt.show()


    def plot_smoothed(self, msm_id, series_name, time_field, value_field, granularity, with_original, with_smoothed, start_coex = None, stop_coex = None):
        """
        Plot a smoothed version of a time series for a measurement, with optional original and coexisting application highlighting.
        Args:
            msm_id (str): The measurement ID.
            series_name (str): The name of the series to plot.
            time_field (str): The field name for time.
            value_field (str): The field name for values.
            granularity (str): The resampling granularity (e.g., '1S').
            with_original (bool): Whether to plot the original data.
            with_smoothed (bool): Whether to plot the smoothed data.
            start_coex (float, optional): Start time of coexisting application.
            stop_coex (float, optional): Stop time of coexisting application.
        """
        import matplotlib.pyplot as plt
        import numpy as np
        import pandas as pd
        from scipy.ndimage import gaussian_filter1d

        result = self.find_all_results_by_measurement_id(msm_id=msm_id)
        aois = result[0][series_name]


        timestamps = np.array([aoi_data[time_field] for aoi_data in aois], dtype=float)
        values = np.array([aoi_data[value_field] for aoi_data in aois], dtype=float)
        #timestamps -=timestamps[0]  # NON NECESSARIO PERCHE' USO to_datetime dopo

        df = pd.DataFrame({time_field: timestamps, value_field: values})

        df[time_field] = pd.to_datetime(df[time_field], unit='s')
        #df[time_field] = df[time_field] - df[time_field].iloc[0]
        df.set_index(time_field, inplace=True)

        df_resampled = df.resample(granularity).mean().interpolate()

        smoothed_values = gaussian_filter1d(df_resampled[value_field], sigma=2)

        plt.figure(figsize=(10, 6))

        if with_original:
            plt.plot(df.index, df[value_field], label="Original Data", linestyle='-', marker='o', color='b')
            #plt.plot(df_resampled.index, df_resampled[value_field], label="Original Data", alpha=0.5, linestyle='-', marker='o')

        if with_smoothed:
            plt.plot(df_resampled.index, smoothed_values, label="Smoothed Data", color='red', linewidth=2, linestyle='-', marker='o')

        plt.xlabel("Timestamp")
        plt.ylabel(value_field + " (s)")
        plt.legend()
        plt.title("Smoothed Time Series")
        plt.grid(True)

        if (start_coex is not None) and (stop_coex is not None):
            plt.axvspan(xmin=start_coex, xmax=stop_coex, color='#82B366', alpha=0.3, label="Coexisting Application")

        plt.show()



    def calculate_time_differences(self, seconds_diff):
        """
        Calculate and print time differences between consecutive completed measurements, highlighting those with different types and small time gaps.
        Args:
            seconds_diff (float): The threshold for time difference in seconds.
        """
        # Troviamo tutti i documenti ordinati per start_time in modo decrescente
        cursor = self.measurements_collection.find({"state": "completed"}).sort("start_time", 1)

        previous_start_time = None
        previous_id = None
        previous_type = None
        differences = []

        # Iteriamo sui documenti
        for document in cursor:
            current_start_time = document["start_time"]
            current_id = document["_id"]
            current_type = document["type"]

            # Se c'è un documento precedente, calcoliamo la differenza
            if previous_start_time is not None:
                time_difference = previous_start_time - current_start_time
                differences.append((current_start_time, time_difference))

                # Se la differenza è inferiore ai 60 secondi e i tipi sono diversi, stampiamo gli ID dei documenti
                if abs(time_difference) < seconds_diff and previous_type != current_type:
                    print("*******************INIZIO*******************")
                    print(f"Time Difference: {time_difference} seconds")
                    print(f"ID of Previous Document: {previous_id}")
                    print(f"ID of Current Document: {current_id}")
                    print(f"Type of Previous Document: {previous_type}")
                    print(f"Type of Current Document: {current_type}")
                    print("*******************FINE*******************")
                    print("\n")

            # Aggiorniamo previous_start_time, previous_id e previous_type per il prossimo ciclo
            previous_start_time = current_start_time
            previous_id = current_id
            previous_type = current_type


    # ------------------------------------------------- RESULTS COLLECTION -------------------------------------------------

    def convert_objectid(self, obj):
        """
        Convert a BSON ObjectId to a string for JSON serialization.
        Args:
            obj: The object to convert.
        Returns:
            str: The string representation of the ObjectId.
        Raises:
            TypeError: If the object is not an ObjectId.
        """
        if isinstance(obj, ObjectId):
            return str(obj)
        raise TypeError("Type not serializable")

    def insert_result(self, result) -> str:
        """
        Insert a result document into the results collection.
        If MongoDB is unavailable, store the result locally as a JSON file.
        Args:
            result: The result object to insert (must have to_dict method).
        Returns:
            str or dict: The inserted result's ID, or a dict with local storage info on failure.
        """
        try:
            insert_result = self.results_collection.insert_one(result.to_dict())
            if insert_result.inserted_id:
                print(f"MongoDB: result stored in mongo. Result ID -> |{insert_result.inserted_id}|")
            
            return insert_result.inserted_id
        except Exception as e:
            result._id = ObjectId()
            filename = f"{result.msm_id}.json"
            base_path = os.path.join(Path(__file__).parent, "json", filename)
            with open(base_path, "w", encoding="utf-8") as file:
                json.dump(result.to_dict(), file, indent=4, ensure_ascii=False, default=self.convert_objectid)
            
            print(f"MongoDB: Error while storing the result on mongo -> {e}")
            print(f"Result stored locally in: {base_path}")
            return {"_id": result._id, "locally": True}

    """
    def insert_iperf_result(self, result : IperfResultModelMongo) -> str:
        try:
            insert_result = self.results_collection.insert_one(result.to_dict())
            if insert_result.inserted_id:
                print(f"MongoDB: iperf result stored in mongo. Result ID -> |{insert_result.inserted_id}|")
                return insert_result.inserted_id
        except Exception as e:
            print(f"MongoDB: Error while storing the Iperf result on mongo -> {e}")
            return None
    """

    """
    def insert_ping_result(self, result : PingResultModelMongo) -> str:
        try:
            insert_result = self.results_collection.insert_one(result.to_dict())
            if insert_result.inserted_id:
                print(f"MongoDB: ping result stored in mongo. Result ID -> |{insert_result.inserted_id}|")
                return insert_result.inserted_id
        except Exception as e:
            print(f"MongoDB: Error while storing the Ping result on mongo -> {e}")
            return None
    """
    
    """
    def insert_energy_result(self, result : EnergyResultModelMongo):
        try:
            insert_result = self.results_collection.insert_one(result.to_dict())
            if insert_result.inserted_id:
                print(f"MongoDB: energy result stored in mongo. Result ID -> |{insert_result.inserted_id}|")
                return insert_result.inserted_id
        except Exception as e:
            print(f"MongoDB: Error while storing the Energy result on mongo -> {e}")
            return None
    """

    def delete_results_by_msm_id(self, msm_id) -> bool:
        """
        Delete all result documents associated with a measurement ID.
        Args:
            msm_id (str): The measurement ID.
        Returns:
            bool: True if any results were deleted, False otherwise.
        """
        delete_result = self.results_collection.delete_many(
                            {"msm_id": ObjectId(msm_id)})
        return (delete_result.deleted_count > 0)
    

    def delete_result_by_id(self, result_id : str) -> bool:
        """
        Delete a result document by its ID.
        Args:
            result_id (str): The result ID to delete.
        Returns:
            bool: True if deleted, False otherwise.
        """
        delete_result = self.results_collection.delete_one(
                            {"_id": ObjectId(result_id)})
        return (delete_result.deleted_count > 0)
      
    
    def find_all_results_by_measurement_id(self, msm_id):
        """
        Find all result documents associated with a measurement ID.
        Args:
            msm_id (str): The measurement ID.
        Returns:
            list: List of result documents or an error model as dict.
        """
        try:
            cursor = self.results_collection.find({"msm_id": ObjectId(msm_id)})
            result_list = list() if (cursor is None) else list(cursor)
            return result_list
        except Exception as e:
            print(f"MongoDB: exception handled for find_all_result. Reason: {e}")
            find_result = ErrorModel(object_ref_id=msm_id, object_ref_type="results", 
                                     error_description="It must be a 12-byte input or a 24-character hex string",
                                     error_cause="measurement_id NOT VALID")
        return (find_result.to_dict())