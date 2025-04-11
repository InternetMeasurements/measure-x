import time, os
from pathlib import Path
from bson import ObjectId
from datetime import datetime
from pymongo import MongoClient
from modules.configLoader.config_loader import ConfigLoader, MONGO_KEY
from modules.mongoModule.models.error_model import ErrorModel
from modules.mongoModule.models.measurement_model_mongo import MeasurementModelMongo
import matplotlib.pyplot as plt
import numpy as np, json
import pandas as pd
from scipy.ndimage import gaussian_filter1d

def main():
    try:
        cl = ConfigLoader(base_path = Path(__file__).parent, file_name="coordinatorConfig.yaml", KEY = MONGO_KEY)
        mongo_db = MongoDB(mongo_config = cl.config)

        #msm_ids = ["67ebf8ea8987f51dc2df77b5", "67ebf9568987f51dc2df77b7", "67ebf9a48987f51dc2df77b9", "67ebf9b88987f51dc2df77bb","67ebf9d48987f51dc2df77bd","67ebfa408987f51dc2df77c0","67ebfa898987f51dc2df77c3"]
        # msm_ids = ["67ed11eaa31b5fb523fb66ea", "67ed1133a31b5fb523fb66e8", "67ed0c36a31b5fb523fb66db", "67ed0d0ca31b5fb523fb66dd", "67ed0e10a31b5fb523fb66df", "67ed0eeaa31b5fb523fb66e1", "67ed0ff6a31b5fb523fb66e3"]
        #msm_ids = ["67eceb8bf753918166cc5018", "67ecebddf753918166cc501a", "67ecec25f753918166cc501c", "67ecec7af753918166cc501e", "67eced60f753918166cc5020", "67ecedcff753918166cc5023", "67ecee67f753918166cc5026"]
        #msm_ids = ["67ed11eaa31b5fb523fb66ea", "67ed1133a31b5fb523fb66e8", "67ed0c36a31b5fb523fb66db"]
        #msm_ids = ["67ed45b0a44dc36adbccf3a2", "67ed45c5a44dc36adbccf3a3"]
        #msm_ids = ["67ed484aa44dc36adbccf3a6", "67ed484ea44dc36adbccf3a7"]
        #msm_ids = ["67ed49f5a44dc36adbccf3aa", "67ed49faa44dc36adbccf3ab"]
        #msm_ids = ["67ed4b3ca44dc36adbccf3ae", "67ed4b3fa44dc36adbccf3af"]
        #msm_ids = ["67ed4c1fa44dc36adbccf3b2", "67ed4d37a44dc36adbccf3b7"]
        msm_ids = ["67ed3d15c045f209793ab8fe"]
        aoi_value = []
        for msm_id in msm_ids:
            mongo_db.get_aoi_avg_min_max(msm_id, "min")#aoi_value.append(mongo_db.get_aoi_avg_min_max(msm_id, "min"))
        
        #mongo_db.plot_aoi(aoi_value, "min")
    except Exception as e:
        print(f"Coordinator: connection failed to mongo. -> Exception info: \n{e}")
        return
    



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
    
    def find_all_results_by_measurement_id(self, msm_id):
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

    def plot_smoothed(self, msm_id, series_name, time_field, value_field, granularity, with_original, with_smoothed, start_coex = None, stop_coex = None):
        result = self.find_all_results_by_measurement_id(msm_id=msm_id)
        aois = result[0][series_name]


        timestamps = np.array([aoi_data[time_field] for aoi_data in aois], dtype=float)
        values = np.array([aoi_data[value_field] for aoi_data in aois], dtype=float)
        timestamps -=timestamps[0]  # NON NECESSARIO PERCHE' USO to_datetime dopo

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
            plt.plot(df_resampled.index, smoothed_values, label="Resempled Data", color='red', linewidth=2, linestyle='-', marker='o', markersize=2)

        plt.xlabel("Timestamp", fontsize=14)
        plt.ylabel(value_field + " (mS)", fontsize=14)
        plt.rcParams['font.size'] = 14
        plt.tick_params(axis='y', labelsize=14) 
        plt.tick_params(axis='x', labelsize=14) 
        plt.legend()
        plt.title("AoI Time Series")
        plt.grid(axis='x')

        if (start_coex is not None) and (stop_coex is not None):
            plt.axvspan(xmin=start_coex, xmax=stop_coex, color='#82B366', alpha=0.3, label="Coexisting Application")

        plt.show()

    
    def get_aoi_avg_min_max(self, msm_id, param):
        result = self.find_all_results_by_measurement_id(msm_id=msm_id)

        if result == []:
            print(f"No result in DB for -> {msm_id}")
            return
        
        filename = f"{msm_id}.json"
    
        # Scrive il risultato in un file JSON
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(result, file, indent=4, ensure_ascii=False, default=self.convert_objectid)
        
        print(f"File salvato: {filename}")
        
        """
        aois = result[0]["aois"]
        values = np.array([aoi_data["AoI"] for aoi_data in aois], dtype=float)
        if param == "mean":
            return values.mean()
        elif param == "min":
            return values.min()
        elif param == "max":
            return values.max()
        return -1"
        """

    def plot_aoi(self, aoi_values, param):
        x_values = list(range(1, len(aoi_values) + 1))

        # Creazione del grafico
        plt.figure(figsize=(8, 5))
        plt.plot(x_values, aoi_values, marker='o', linestyle='-', color='b', label=f"AoI {param}")

        # Etichette e titolo
        plt.xlabel("Experiment Number")  # Etichetta asse X
        plt.ylabel(f"AoI {param} Value")  # Etichetta asse Y
        plt.title(f"AoI {param} Over Experiments")  # Titolo del grafico
        plt.grid(True)  # Mostra la griglia
        plt.legend()  # Mostra la legenda

        # Mostra il grafico
        plt.show()
                

    def convert_objectid(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        raise TypeError("Type not serializable")

if __name__ == "__main__":
    main()