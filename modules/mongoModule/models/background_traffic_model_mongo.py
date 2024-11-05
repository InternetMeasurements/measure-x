class BackgroundTrafficModelMongo:
    def __init__(self, description, source_probe, dest_probe, type):
        self.id = None
        self.description = description
        self.source_probe = source_probe
        self.dest_probe = dest_probe
        self.type = type
    