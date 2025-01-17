class ErrorModel():
    # This class describes an object to have more info about occurred error 
    def __init__(self, object_ref_id = None, object_ref_type = None, error_description = None, error_cause = None):
        self.object_ref_id = object_ref_id
        self.object_ref_type = object_ref_type
        self.error_description = error_description
        self.error_cause = error_cause
