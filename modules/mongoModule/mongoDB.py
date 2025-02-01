import time
from bson import ObjectId
from pymongo import MongoClient
from modules.mongoModule.models.error_model import ErrorModel
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from modules.mongoModule.models.ping_result_model_mongo import PingResultModelMongo
from modules.mongoModule.models.iperf_result_model_mongo import IperfResultModelMongo
from modules.mongoModule.models.coexisting_application_model_mongo import CoexistingApplicationModelMongo

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

    
    def insert_measurement(self, measure : MeasurementModelMongo) -> str:
        try:
            measure.start_time = time.time()
            measure.state = STARTED_STATE
            insert_result = self.measurements_collection.insert_one(measure.to_dict())
            if insert_result.inserted_id:
                print(f"MongoDB: measurement stored in mongo. ID -> |{insert_result.inserted_id}|")
                return insert_result.inserted_id
        except Exception as e:
            print(f"MongoDB: Error while storing the measurment on mongo -> {e}")
            return None
        

    def insert_iperf_result(self, result : IperfResultModelMongo) -> str:
        try:
            insert_result = self.results_collection.insert_one(result.to_dict())
            if insert_result.inserted_id:
                print(f"MongoDB: iperf result stored in mongo. ID -> |{insert_result.inserted_id}|")
                return insert_result.inserted_id
        except Exception as e:
            print(f"MongoDB: Error while storing the Iperf result on mongo -> {e}")
            return None


    def insert_ping_result(self, result : PingResultModelMongo) -> str:
        try:
            insert_result = self.results_collection.insert_one(result.to_dict())
            if insert_result.inserted_id:
                print(f"MongoDB: ping result stored in mongo. ID -> |{insert_result.inserted_id}|")
                return insert_result.inserted_id
        except Exception as e:
            print(f"MongoDB: Error while storing the Ping result on mongo -> {e}")
            return None


    def set_measurement_as_completed(self, measurement_id) -> bool:
        stop_time = time.time()
        update_result = self.measurements_collection.update_one(
                            {"_id": ObjectId(measurement_id)},
                            {"$set": {"stop_time": stop_time,
                                      "state": COMPLETED_STATE} })
        return (update_result.modified_count > 0)
    

    def delete_measurements_by_id(self, measurement_id: str) -> bool:
        delete_result = self.measurements_collection.delete_one(
                            {"_id": ObjectId(measurement_id)})
        return (delete_result.deleted_count > 0)
    

    def delete_results_by_measure_reference(self, measure_reference) -> bool:
        delete_result = self.results_collection.delete_many(
                            {"measure_reference": ObjectId(measure_reference)})
        return (delete_result.deleted_count > 0)
    

    def delete_result_by_id(self, result_id : str) -> bool:
        delete_result = self.results_collection.delete_one(
                            {"_id": ObjectId(result_id)})
        return (delete_result.deleted_count > 0)
    

    def set_measurement_as_failed_by_id(self, measurement_id : str) -> bool:
        replace_result = self.measurements_collection.update_one(
                            {"_id": ObjectId(measurement_id)},
                            {"$set":{
                                "_id": ObjectId(measurement_id),
                                "state": FAILED_STATE
                                }
                            })
        return (replace_result.modified_count > 0)
    

    def find_measurement_by_id(self, measurement_id):
        try:
            find_result = self.measurements_collection.find_one({"_id": ObjectId(measurement_id)})
            if find_result is None:
                find_result = ErrorModel(object_ref_id=measurement_id, object_ref_type="measurement",
                                         error_description="Measurement not found in DB",
                                         error_cause="Wrong measurement_id")
            else:
                find_result = MeasurementModelMongo.cast_dict_in_MeasurementModelMongo(find_result)
        except Exception as e:
            print(f"Motivo -> {e}")
            find_result = ErrorModel(object_ref_id=measurement_id, object_ref_type="measurement", 
                                     error_description="It must be a 12-byte input or a 24-character hex string",
                                     error_cause="measurement_id NOT VALID")
        return (find_result.to_dict())
    

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
    
    def find_all_results_by_measurement_id(self, measurement_id):
        try:
            cursor = self.results_collection.find({"measure_reference": ObjectId(measurement_id)})
            documents = list(cursor)
            result_list = []
            for document in documents:
                if 'measure_reference' in document:
                    result_list.append(document)
                    #if measurement_type == "iperf":
            print(f"lista-> {result_list} ")
            return result_list
        except Exception as e:
            print(f"Motivo -> {e}")
            find_result = ErrorModel(object_ref_id=measurement_id, object_ref_type="list of results", 
                                     error_description="It must be a 12-byte input or a 24-character hex string",
                                     error_cause="measurement_id NOT VALID")
        return (find_result.to_dict())