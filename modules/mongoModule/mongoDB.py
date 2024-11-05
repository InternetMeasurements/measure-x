from pymongo import MongoClient
from src.modules.mongoModule.measurement_model_mongo import MeasurementModelMongo, BackgroundTrafficModelMongo

class MongoDB:
    def __init__(self):
        self.addr_mongo_server = "192.168.1.102"
        self.user = "measurex"
        self.password = "measurex"
        self.db_name = "measurex"
        self.results_collection = None
        self.measurements_collection = None
        #self.client = MongoClient("mongodb://" + self.user + ":" + self.password + "@" + self.addr_mongo_server + ":27017/" + self.db_name)
        self.client = MongoClient("mongodb://measurex:measurex@192.168.1.102:27017/")

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
    
    def insert_measurement(self, measure : MeasurementModelMongo) -> bool:
        try:
            insert_result = self.measurements_collection.insert_one(measure.to_dict())
            if insert_result.inserted_id:
                print(f"Measurement stored in mongo. ID -> |{insert_result.inserted_id}|")
                return True
        except Exception as e:
            print(f"Error while storing the measurment on mongo -> {e}")
            return False
    

    def delete_result_by_id(id : str) -> bool:
        return False