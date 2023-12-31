from datetime import datetime, timedelta
import logging
from pathlib import Path

from cdk.services.api.energi_data_service import EnergiDataService
from cdk.common_modules.access.secrets import Secrets
from cdk.common_modules.spark.spark_config import SparkConfig
from cdk.common_modules.spark.spark_session_builder import SparkSessionBuilder
from cdk.common_modules.delta_stores.delta_state import DeltaState
from cdk.common_modules.utility.logging import Logger

# Set logging
Logger = Logger(Path(__file__).stem)

Logger.addLoggingLevel('APPINFO', logging.INFO - 5)

logger = Logger.get_logger()

storage_account_name = "adlsthuehomelakehousedev"

# Set Spark configurations
logger.appinfo("Setting Spark configurations")
spark_config = SparkConfig(Secrets())

# Add jars to install
logger.appinfo("Adding jars to install")
spark_config.add_jars_to_install(['hudi', 'azure_storage'])

# Add storage account access
logger.appinfo("Adding storage account access")
spark_config.add_storage_account_access(storage_account_name, method='access_key')

# Build SparkSession
logger.appinfo("Building SparkSession")
spark = SparkSessionBuilder("ElectricityConsumptionIndustry", spark_config).build()

# Set dataset name and landing path
dataset_name = "ConsumptionDK3619codehour"
dataset_path = "energi_data_service"
container_name = "bronze"

# landing_path = f"hdfs://namenode:9000/data/landing/energi_data_service/{dataset_name}"
bronze_path = f"abfss://{container_name}@{storage_account_name}.dfs.core.windows.net/{dataset_path}"



# Set Hudi options
hudi_options = {
    'hoodie.table.name': dataset_name,
    'hoodie.datasource.write.keygenerator.class': 'org.apache.hudi.keygen.ComplexKeyGenerator',
    'hoodie.datasource.write.recordkey.field': 'HourUTC,DK19Code,DK36Code',
    'hoodie.datasource.write.partitionpath.field': '',
    'hoodie.datasource.write.table.type': 'COPY_ON_WRITE',
    'hoodie.datasource.write.table.name': dataset_name,
    'hoodie.datasource.write.operation': 'upsert',
    'hoodie.datasource.write.precombine.field': 'HourUTC',
    'hoodie.upsert.shuffle.parallelism': 1,
    'hoodie.insert.shuffle.parallelism': 1
}

# The api will have a lag of 8 days
max_date = datetime.strptime('2023-09-02T00:00', "%Y-%m-%dT%H:%M") # datetime.today() - timedelta(days=8) 

# Create DeltaState object
logger.appinfo("Creating DeltaState object")
delta_state = DeltaState(spark, storage_account_name, container_name, dataset_path + dataset_name, dataset_name)

while True:
    # Get the delta state
    delta_state_value = delta_state.get_delta_state(default_value='2023-09-01T00:00')
    logger.appinfo(f"Delta state: {delta_state_value}")

    # Increment the delta state by one day
    end_date = datetime.strptime(delta_state_value, "%Y-%m-%dT%H:%M") + timedelta(days=1)

    # Get the data
    logger.appinfo(f"Getting data from {delta_state_value} to {end_date.strftime('%Y-%m-%dT%H:%M')}")
    data = EnergiDataService(dataset_name).get_data(delta_state_value, end_date.strftime("%Y-%m-%dT%H:%M"))

    try:
        # Load the data into a DataFrame
        df = spark.createDataFrame(data)
    except Exception as e:
        if "empty dataset" in str(e):
            logger.appinfo(f"No data found. Should be checked manually that there is no data from {delta_state_value} to {end_date.strftime('%Y-%m-%dT%H:%M')}")
            break
        else:
            raise e

    # Log the number of rows written
    logger.appinfo(f"Number of rows written: {df.count()}")

    # Write the DataFrame to Hudi
    df.write.format("org.apache.hudi"). \
        options(**hudi_options). \
        mode("append"). \
        save(bronze_path)

    # Update the delta state
    delta_state.set_delta_state(end_date.strftime("%Y-%m-%dT%H:%M"))

    # Break if the end date is greater than or equal to today
    if end_date >= max_date:
        logger.appinfo("End date is greater than or equal to today")
        break