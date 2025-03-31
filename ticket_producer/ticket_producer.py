from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic
from faker import Faker
import json
import time
import random
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

#Configuration Kafka
conf = {
    'bootstrap.servers': 'redpanda:9092',
    'security.protocol': 'SASL_PLAINTEXT',
    'sasl.mechanisms': 'SCRAM-SHA-256',
    'sasl.username': os.getenv('KAFKA_USERNAME'),
    'sasl.password': os.getenv('KAFKA_PASSWORD'),
    'client.id': 'ticket-producer'
}

# Vérifie si le topic existe, sinon le crée
admin_client = AdminClient(conf)
topic_name = "client_tickets"
topics = admin_client.list_topics(timeout=10).topics

if topic_name not in topics:
    print(f"Topic '{topic_name}' non trouvé, création...")
    new_topic = NewTopic(topic_name, num_partitions=1, replication_factor=1)
    fs = admin_client.create_topics([new_topic])
    for topic, f in fs.items():
        try:
            f.result()
            print(f"✅ Topic '{topic}' créé avec succès.")
        except Exception as e:
            print(f"❌ Erreur lors de la création du topic '{topic}': {e}")
else:
    print(f"Topic '{topic_name}' déjà existant.")


# Initialisation du producteur Kfka
producer = Producer(conf)
faker = Faker()
ticket_counter = 1

def generate_ticket():
    """Génère un ticket client aléatoire."""
    global ticket_counter 
    ticket_id = f"TICKET-{ticket_counter:04d}"  # Format TICKET-0001, TICKET-0002...
    ticket_counter += 1

    date = faker.date_time_between(start_date=datetime(2025, 1, 1), end_date="now")
    
    ticket = {
        "ticket_id": ticket_id,
        "client_id": faker.random_int(min=1000, max=9999),
        "created_at": date.isoformat(),
        "request": faker.sentence(),
        "request_type": random.choice(["support", "billing", "technical", "other"]), 
        "priority": random.choice(["low", "medium", "high"]) 
    }
    return ticket

def delivery_report(err, msg):
    """Callback après envoi d'un message."""
    if err:
        print(f"Erreur lors de l'envoi du message : {err}")
    else:
        print(f"Message envoyé : {msg.value().decode('utf-8')}")

nb_tickets = 100

for n in range(nb_tickets):
    ticket = generate_ticket()  
    producer.produce("client_tickets", key=str(ticket["ticket_id"]), value=json.dumps(ticket), callback=delivery_report)
    producer.flush() 

print(nb_tickets, " tickets ont été envoyés à Redpanda !")
