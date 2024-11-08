import time
from bson import ObjectId
from pymongo import MongoClient
from src.modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
from src.modules.mongoModule.models.ping_result_model_mongo import PingResultModelMongo
from src.modules.mongoModule.models.iperf_result_model_mongo import IperfResultModelMongo
from src.modules.mongoModule.models.background_traffic_model_mongo import BackgroundTrafficModelMongo

class MongoDB:
    def __init__(self):
        self.addr_mongo_server = "192.168.1.117" 
        self.user = "measurex"
        self.password = "measurex"
        self.db_name = "measurex"
        self.results_collection = None
        self.measurements_collection = None
        self.client = MongoClient("mongodb://" + self.user + ":" + self.password + "@" + self.addr_mongo_server + ":27017/")

        db = self.client[self.db_name] # crea il db measurex

        if "measurements" not in db.list_collection_names(): # if the measurements_collection doesn't exists, then creates it
            db.create_collection("measurements")

        if "results" not in db.list_collection_names():  # if the results_collection doesn't exists, then creates it
            db.create_collection("results")
        
        self.measurements_collection = db["measurements"]
        self.results_collection = db["results"]

        #measurements_collection.insert_one({})
        #results_collection.insert_one()
        """
        print("Collezioni esistenti: ")
        print(db.list_collection_names())

        measurements_data = self.measurements_collection.find()
        print("Dati dalla collezione 'measurements':")
        for measurement in measurements_data:
            print(f"id: {measurement['_id']}")
            delete_result = measurements_collection.delete_one({"_id": measurement['_id']})
            if delete_result.deleted_count > 0:
                print("eliminato")
            else:
                print("non eliminato")

        results_data = results_collection.find()
        print("\nDati dalla collezione 'results':")
        for result in results_data:
            print(result)
            delete_result = results_collection.delete_one({'_id': result['_id']})
            if delete_result.deleted_count > 0:
                print("eliminato")
            else:
                print("non eliminato")
        """
    
    def insert_measurement(self, measure : MeasurementModelMongo) -> str:
        try:
            measure.start_time = time.time()
            measure.state = "started"
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
                                      "state": "completed"} })
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
    
    def set_measurement_as_failed(self, measurement_id : str) -> bool:
        replace_result = self.measurements_collection.update_one(
                            {"_id": ObjectId(measurement_id)},
                            {"$set":{
                                "_id": ObjectId(measurement_id),
                                "state": "failed"
                                }
                            })
        return (replace_result.modified_count > 0)