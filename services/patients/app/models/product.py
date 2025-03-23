from config import db

class Product:
    collection = db["products"]

    @staticmethod
    def create_product(data):
        return Product.collection.insert_one(data)

    @staticmethod
    def get_products():
        return list(Product.collection.find({}, {"_id": 0}))
