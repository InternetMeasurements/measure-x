import time
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

    def __init__(self, mongo_config):
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
        result = self.measurements_collection.replace_one({"_id": ObjectId(measurement_id)}, measure.to_dict(to_store = True))
        return (result.matched_count > 0)

    def set_measurement_as_completed(self, measurement_id) -> bool:
        stop_time = time.time()
        update_result = self.measurements_collection.update_one(
                            {"_id": ObjectId(measurement_id)},
                            {"$set": {"stop_time": stop_time,
                                      "state": COMPLETED_STATE} })
        return (update_result.modified_count > 0)


    def set_measurement_as_failed_by_id(self, measurement_id : str) -> bool:
        replace_result = self.measurements_collection.update_one(
                            {"_id": ObjectId(measurement_id)},
                            {"$set":{
                                "_id": ObjectId(measurement_id),
                                "state": FAILED_STATE
                                }
                            })
        return (replace_result.modified_count > 0)
    
    
    def update_results_array_in_measurement(self, msm_id):
    # This method is an automatic setting of the results doc-linking in measurements collection. 
    # It finds all the results with that msm_id, and store them _ids in the doc-link
        try:
            update_result = self.measurements_collection.update_one(
                {"_id": ObjectId(msm_id)},
                {"$set": {"results": list(
                    self.results_collection.find({"msm_id": ObjectId(msm_id)}).distinct("_id"))}}
            )
            return update_result
        except Exception as e:
            print(f"Motivo -> {e}")
            find_result = ErrorModel(object_ref_id = msm_id, object_ref_type="list of results", 
                                     error_description="It must be a 12-byte input or a 24-character hex string",
                                     error_cause="measurement_id NOT VALID")
        return (find_result.to_dict())
    

    def delete_measurements_by_id(self, measurement_id: str) -> bool:
        # Da cancellare
        delete_result = self.measurements_collection.delete_one(
                            {"_id": ObjectId(measurement_id)})
        return (delete_result.deleted_count > 0)


    def find_measurement_by_id(self, measurement_id):
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
        measurement_result : MeasurementModelMongo = self.measurements_collection.find_one({"_id": ObjectId(measurement_id)})
        if measurement_result is None:
            return None
        return (measurement_result.state)
    
    
    def get_old_measurements_not_yet_setted_as_failed(self) -> list[MeasurementModelMongo]:
        twenty_four_hours_ago  = time.time() - SECONDS_OLD_MEASUREMENT
        old_measurements = self.measurements_collection.find(
                            {"start_time": {"$lt": twenty_four_hours_ago},
                             "state": STARTED_STATE})
        return list(old_measurements)
    
    
    def set_old_measurements_as_failed(self) -> int:
        twenty_four_hours_ago  = time.time() - SECONDS_OLD_MEASUREMENT
        replace_result = self.measurements_collection.update_many(
                            { "start_time": {"$lt": twenty_four_hours_ago} ,
                              "state": STARTED_STATE },
                            {"$set":{
                                "state": FAILED_STATE
                                }
                            })
        return replace_result.modified_count
    
    def find_and_plot(self, msm_id, start_coex, stop_coex, series_name, time_field, value_field):
        import matplotlib.pyplot as plt
        import numpy as np

        result = self.find_all_results_by_measurement_id(msm_id=msm_id)
        aois = result[series_name]


        timestamps = np.array([aoi_data[time_field] for aoi_data in aois], dtype=float)
        aoi_values = np.array([aoi_data[value_field] for aoi_data in aois], dtype=float)

        timestamps -= timestamps[0]

        plot_name = "Energy" if value_field == "Current" else "AoI"
        plt.figure(figsize=(10, 6))

        plt.plot(timestamps, aoi_values, marker='o', linestyle='-', color='#B85450', label=value_field)
        plt.xlabel("Timestamp (s)", fontsize=16)

        ylabel = "AoI (s)" if plot_name == "AoI" else "Current (A)"
        plt.ylabel(ylabel, fontsize=16)

        if plot_name == "AoI":
            plt.axvspan(xmin=start_coex, xmax=stop_coex, color='#82B366', alpha=0.3, label="Coexisting Application")

        plt.rcParams['font.size'] = 14
        plt.xticks(np.arange(0, timestamps[-1], 2), fontsize=16)
        plt.yticks(fontsize=16)

        plt.title("Measuring " + plot_name + ("" if plot_name == "Energy" else " with Coexisting Application traffic"),  fontsize=16)
        plt.grid(axis='x')
        plt.legend()
        plt.show()




    def calculate_time_differences(self, seconds_diff):
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

    def insert_result(self, result) -> str:
        try:
            insert_result = self.results_collection.insert_one(result.to_dict())
            if insert_result.inserted_id:
                print(f"MongoDB: result stored in mongo. Result ID -> |{insert_result.inserted_id}|")
                return insert_result.inserted_id
        except Exception as e:
            print(f"MongoDB: Error while storing the result on mongo -> {e}")
            return None

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
        delete_result = self.results_collection.delete_many(
                            {"msm_id": ObjectId(msm_id)})
        return (delete_result.deleted_count > 0)
    

    def delete_result_by_id(self, result_id : str) -> bool:
        delete_result = self.results_collection.delete_one(
                            {"_id": ObjectId(result_id)})
        return (delete_result.deleted_count > 0)
      
    
    def find_all_results_by_measurement_id(self, msm_id):
        try:
            cursor = self.results_collection.find({"msm_id": ObjectId(msm_id)})
            result_list = list() if (cursor is None) else list(cursor)
            if len(result_list) == 1:
                return result_list[0]
            return result_list
        except Exception as e:
            print(f"Motivo -> {e}")
            find_result = ErrorModel(object_ref_id=msm_id, object_ref_type="list of results", 
                                     error_description="It must be a 12-byte input or a 24-character hex string",
                                     error_cause="measurement_id NOT VALID")
        return (find_result.to_dict())