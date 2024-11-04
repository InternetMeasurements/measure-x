from pymongo import MongoClient

class MongoDB:
    def __init__(self):
        self.addr_mongo_server = "192.168.1.102"
        self.user = "measurex"
        self.password = "measurex"
        self.db_name = "measurex"
        self.results_collection_name = "results"
        self.measurements_collection_name = "measurements"
        #self.client = MongoClient("mongodb://" + self.user + ":" + self.password + "@" + self.addr_mongo_server + ":27017/" + self.db_name)
        self.client = MongoClient("mongodb://measurex:measurex@192.168.1.102:27017/")

        db = self.client[self.db_name] # crea il db measurex

        if self.measurements_collection_name not in db.list_collection_names():
            db.create_collection(self.measurements_collection_name)

        if self.results_collection_name not in db.list_collection_names():
            db.create_collection(self.results_collection_name)
        
        measurements_collection = db["measurements"]
        results_collection = db["results"]

        measurements_collection.insert_one({})
        results_collection.insert_one()

        print("Collezioni create:")
        print(db.list_collection_names())
"""
        measurements_data = measurements_collection.find()
        print("Dati dalla collezione 'measurements':")
        for measurement in measurements_data:
            print(measurement)

        results_data = results_collection.find()
        print("\nDati dalla collezione 'results':")
        for result in results_data:
            print(result)
"""
