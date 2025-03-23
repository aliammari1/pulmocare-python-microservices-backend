from pymongo import MongoClient
import os

def get_database():
    client = MongoClient('mongodb://admin:admin@localhost:27017/')
    return client['medapp']
