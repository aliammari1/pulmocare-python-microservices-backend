import os

from pymongo import MongoClient
from services.logger_service import logger_service


def get_database():
    client = MongoClient(f"mongodb://admin:admin@{self.config.MONGODB_HOST}:27017/")
    return client["medapp"]
