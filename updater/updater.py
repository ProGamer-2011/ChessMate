import json
from pathlib import Path


class Updater:

    def __init__(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.version_file = self.project_root / "version.json"

        self.current_version = None
        self.current_build = None

        self.load_local_version()

    def load_local_version(self):
        with open(self.version_file, "r", encoding="utf-8") as file:
            data = json.load(file)

        self.current_version = data["version"]
        self.current_build = data["build"]

    def get_version(self):
        return self.current_version

    def get_build(self):
        return self.current_build