#Database Credentials
DATABASE_IP = "localhost" #IP of the mysql database
DATABASE_NAME = "nameHere" #Name of the database
DATABASE_USER = "unameHere" #Name of the database user
DATABASE_PASS = "passHere" #Database password

#MQTT Broker Credentials
MQTT_ENABLE = False
MQTT_BROKER_ADDR = "IP_HERE" #IP of MQTT broker (should be server IP)
MQTT_BROKER_PORT = 1883 #Port # for MQTT broker (should be 1883) YOU WILL NEED TO TCP PORT FOWARD THIS
MQTT_UNAME = "unameHere" #Username used to connect to MQTT broker
MQTT_PASS = "passHere" #Password used to connect to MQTT broker

#Frequency Settings
ACTIVITY_AGE = 24 #In hours, how old an activity log enty can be for it to be read. Anything older will be ingnored
UPDATE_FREQ = 30 #In seconds, how frequent the online counter should update

#Discord Webhook URL
WEBHOOK_URL = "URL_HERE"

#Count History Settings
AVG_COUNT_ENABLE = True #Enable the average count feature  
FILE_DIR = "countHistory/" #Directory to store the count history files (must end with /)
CSV_FILE = "playerCountHistory.csv" #Player Count History CSV File
DAY_AVG_GRAPH = "dayAvgGraph.png" #Day Average Graph picture
WEEK_AVG_GRAPH = "weekAvgGraph.png" #Week Average Graph picture

#Should only edit if you are to add more worlds
worldDict = {
        1000: {
            "name": "Venture Explorer",
            "pop": 0
            },
        1001: {
            "name": "Return to Venture Explorer",
            "pop": 0
            },
        1100: {
            "name": "Avant Gardens",
            "pop": 0
            },
        1101: {
            "name": "Avant Gardens Survival",
            "pop": 0
            },
        1102: {
            "name": "Spider Queen Battle",
            "pop": 0
            },
        1150: {
            "name": "Block Yard",
            "pop": 0
            },
        1151: {
            "name": "Avant Grove",
            "pop": 0
            },
        1200: {
            "name": "Nimbus Station",
            "pop": 0
            },
        1201: {
            "name": "Pet Cove",
            "pop": 0
            },
        1203: {
            "name": "Vertigo Loop Racetrack",
            "pop": 0
            },
        1204: {
            "name": "Battle of Nimbus Station",
            "pop": 0
            },
        1250: {
            "name": "Nimbus Rock",
            "pop": 0
            },
        1251: {
            "name": "Nimbus Isle",
            "pop": 0
            },
        1300: {
            "name": "Gnarled Forest",
            "pop": 0
            },
        1302: {
            "name": "Canyon Cove",
            "pop": 0
            },
        1303: {
            "name": "Keelhaul Canyon",
            "pop": 0
            },
        1350: {
            "name": "Chantey Shantey",
            "pop": 0
            },
        1400: {
            "name": "Forbidden Valley",
            "pop": 0
            },
        1402: {
            "name": "Forbidden Valley Dragon",
            "pop": 0
            },
        1403: {
            "name": "Dragonmaw Chasm",
            "pop": 0
            },
        1450: {
            "name": "Raven Bluff",
            "pop": 0
            },
        1551: {
            "name": "Frostburgh",
            "pop": 0
            },
        1600: {
            "name": "Starbase 3001",
            "pop": 0
            },
        1601: {
            "name": "Deep Freeze",
            "pop": 0
            },
        1602: {
            "name": "Robot City",
            "pop": 0
            },
        1603: {
            "name": "Moon Base",
            "pop": 0
            },
        1604: {
            "name": "Portabello",
            "pop": 0
            },
        1700: {
            "name": "LEGO Club",
            "pop": 0
            },
        1800: {
            "name": "Crux Prime",
            "pop": 0
            },
        1900: {
            "name": "Nexus Tower",
            "pop": 0
            },
        2000: {
            "name": "Ninjago",
            "pop": 0
            },
        2001: {
            "name": "Frakjaw Battle",
            "pop": 0
            },
        "unknown": {
            "name": "Unknown World ID",
            "pop": 0
            }
}
