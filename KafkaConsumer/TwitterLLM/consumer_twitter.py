from kafka import KafkaConsumer
from concurrent.futures import ThreadPoolExecutor
import requests
import json
from dotenv import load_dotenv
from os import getenv
from pymongo import MongoClient
from datetime import datetime
import google.generativeai as genai

load_dotenv()
api_token = getenv("G2_API_KEY")
mongo_conn_string = getenv("MONGO_CONN_STRING")


# print("Setting up Kafka consumer for ProductHunt topic")
# consumer = KafkaConsumer(
#     'twitter-llm',
#     bootstrap_servers=['localhost:9092'],
#     auto_offset_reset='earliest',
#     enable_auto_commit=True,
#     group_id='producthunt-group',
#     value_deserializer=lambda x: json.loads(x.decode('utf-8')))

# for message in consumer:
#     data = message.value
#     print(data)


load_dotenv()
api_token = getenv("G2_API_KEY")
mongo_conn_string = getenv("MONGO_CONN_STRING")
google_token=getenv("GOOGLE_API_KEY")

# Setup MongoDB connection
client = MongoClient(mongo_conn_string)
db = client.g2hack
unavailable_products_collection = db.unavailableProducts

def ping_mongo():
    try:
        client.server_info()
        print("Connected to MongoDB")
    except:
        print("Failed to connect to MongoDB")

def list_products(api_token, filter_name=None):
    url = "https://data.g2.com/api/v1/products"
    headers = {
        "Authorization": f"Token token={api_token}",
        "Content-Type": "application/vnd.api+json"
    }
    params = {'filter[name]': filter_name} if filter_name else {}

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch products, status code: {response.status_code}")
        return None

def list_products_google(msgData):
    genai.configure(api_key = google_token)
    model = genai.GenerativeModel('gemini-pro')
    response = model.generate_content(f"""{msgData} \n Imagine a digital assistant meticulously analyzing a diverse collection of announcements related to the launch of new products and services in various industries. This assistant is tasked with identifying and categorizing each product or service mentioned, discerning whether each one represents a fresh market entry or an update to an existing offering. The goal is to compile this information into a straightforward, accessible format. Specifically, the assistant is required to present its findings as a list, focusing solely on the names of these products or services, neatly organized into an array. The array should exclusively contain the names, clearly distinguishing between novel introductions and updates to pre-existing entities, thus providing a clear, concise overview of the recent developments highlighted in the announcements.  Give the output in a json format which gives the product name and the status of the same whether its a new product or just a update to the existing product. The status should either be New Product or Update to existing product.""")

    return response.text

def process_message(message_data):
    x=list_products_google(message_data)
    with open("products.json", 'w') as file:
        json.dump(x, file, indent=4)
    with open("products.json", 'r') as file:
        products = json.load(file)
    for product in products:
        if product['status'] == 'New Product':  # Assuming the correct status is "new product"
            product_name = product['product_name']
        if product_name:
            g2_response = list_products(api_token, filter_name=product_name)
            if g2_response and not g2_response.get('data'):
                print(f"Product not found in G2: {product_name}")
                document = {
                    "product_name": product_name,
                    "timestamp": datetime.now()
                }
                unavailable_products_collection.insert_one(document)
            else:
                print(f"Product found in G2: {product_name}")

def main():
    ping_mongo()
    print("Setting up Kafka consumer")
    consumer = KafkaConsumer(
        'twitter-llm',
        bootstrap_servers=['localhost:9092'],
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        group_id='my-group',
        value_deserializer=lambda x: json.loads(x.decode('utf-8')))

    with ThreadPoolExecutor(max_workers=3) as executor:
        for message in consumer:
            data = message.value
            executor.submit(process_message, data)

if __name__ == "__main__":
    main()
