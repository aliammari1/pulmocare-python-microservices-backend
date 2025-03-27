import os

from pymongo import MongoClient


def get_database():
    client = MongoClient("mongodb://admin:admin@localhost:27017/")
    return client["medapp"]
