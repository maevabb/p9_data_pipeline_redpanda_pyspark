from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, when
from pyspark.sql.types import StructType, StringType, IntegerType
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

#env Spark
os.environ["JAVA_HOME"] = os.getenv("JAVA_HOME")
os.environ["SPARK_HOME"] = os.getenv("SPARK_HOME")
os.environ["HADOOP_HOME"] = os.getenv("HADOOP_HOME")

# Spark session
spark = SparkSession.builder \
    .appName("TicketEnrichment") \
    .config("spark.jars.packages", os.getenv("SPARK_PACKAGES")) \
    .getOrCreate()

# Configuration AWS S3
spark._jsc.hadoopConfiguration().set("fs.s3a.access.key", os.getenv("AWS_ACCESS_KEY_ID"))
spark._jsc.hadoopConfiguration().set("fs.s3a.secret.key", os.getenv("AWS_SECRET_ACCESS_KEY"))
spark._jsc.hadoopConfiguration().set("fs.s3a.endpoint", f"s3.{os.getenv('AWS_REGION')}.amazonaws.com")
spark._jsc.hadoopConfiguration().set("fs.s3a.path.style.access", "true")

# Schéma JSON
schema = StructType() \
    .add("ticket_id", StringType()) \
    .add("client_id", IntegerType()) \
    .add("created_at", StringType()) \
    .add("request", StringType()) \
    .add("request_type", StringType()) \
    .add("priority", StringType())

# Lecture continue depuis Redpanda
df_stream = spark.read \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "redpanda:9092") \
    .option("subscribe", "client_tickets") \
    .option("startingOffsets", "earliest") \
    .option("endingOffsets", "latest") \
    .option("kafka.security.protocol", "SASL_PLAINTEXT") \
    .option("kafka.sasl.mechanism", "SCRAM-SHA-256") \
    .option("kafka.sasl.jaas.config",
        f"org.apache.kafka.common.security.scram.ScramLoginModule required username=\"{os.getenv('KAFKA_USERNAME')}\" password=\"{os.getenv('KAFKA_PASSWORD')}\";") \
    .load()


# Parsing
df_parsed = df_stream.selectExpr("CAST(value AS STRING) as json") \
    .select(from_json(col("json"), schema).alias("data")) \
    .select("data.*")

# Ajout de la colonne support_team
df_with_team = df_parsed.withColumn(
    "support_team",
    when(col("request_type") == "technical", "Tech Support")
    .when(col("request_type") == "billing", "Billing Team")
    .when(col("request_type") == "support", "Customer Service")
    .otherwise("General Support")
)

# Agrégation
df_grouped = df_parsed.groupBy("request_type").count()

# Date et chemin S3
export_date = datetime.now().strftime("%Y-%m-%d_%H-%M")
bucket = os.getenv("S3_BUCKET_NAME")

# Export vers S3 en mode batch
df_with_team.write \
    .format("json") \
    .mode("overwrite") \
    .save(f"s3a://{bucket}/batch/{export_date}/enriched_tickets")

df_grouped.write \
    .format("json") \
    .mode("overwrite") \
    .save(f"s3a://{bucket}/batch/{export_date}/ticket_counts_by_type")