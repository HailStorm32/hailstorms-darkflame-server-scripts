import random
import mysql.connector
import paho.mqtt.client as mqtt
from discord_webhook import DiscordWebhook, DiscordEmbed #https://github.com/lovvskillz/python-discord-webhook
import pandas as pd
import matplotlib.pyplot as plt
import json
from datetime import datetime, timezone
import time
import os
from playerCntSettings import *



def getCharStatus(charID, activityDict):
    #Cycle through each entry in the activity log
    #and only look at the most recent entry for each character
    for entry in reversed(activityDict):
        #If the character ID matches and they are online 
        if entry["character_id"] == charID and entry["activity"] == 0:
            return {"isOnline": True, "world": entry["map_id"]}

        #If the character ID matches and they are online 
        elif entry["character_id"] == charID and entry["activity"] == 1:
            return {"isOnline": False, "world": -1}

    #If we have gotten this far without returning, the player isnt in the list
    return {"isOnline": False, "world": -1}

def resetWorldPop(worldDict):
    for worldID in worldDict:
        worldDict[worldID]["pop"] = 0

def updateDiscord(counter_webhook, stats_webhook):
    if AVG_COUNT_ENABLE:
        stats_webhook.remove_file(DAY_AVG_GRAPH)
        stats_webhook.remove_file(WEEK_AVG_GRAPH)
    
    counter_webhook.remove_embeds()
    
    embeds = createEmbeds(numberOnline)

    counter_webhook.add_embed(embeds[0])
    counter_webhook.add_embed(embeds[1])

    if AVG_COUNT_ENABLE:
        with open(FILE_DIR + DAY_AVG_GRAPH, 'rb') as f:
            stats_webhook.add_file(file=f.read(), filename=DAY_AVG_GRAPH)
        with open(FILE_DIR + WEEK_AVG_GRAPH, 'rb') as f:
            stats_webhook.add_file(file=f.read(), filename=WEEK_AVG_GRAPH)

        stats_webhook.content = " "

    if AVG_COUNT_ENABLE:
        stats_webhook.edit()
    counter_webhook.edit()

def createEmbeds(numberOnline):
    embedPlyrCnt = None
    embedWorldPop = None
  

    #Create online players embed
    embedPlyrCnt = DiscordEmbed(title="Online Players", color="03b2f8")

    embedPlyrCnt.set_footer(text="Last updated:")
    embedPlyrCnt.set_timestamp()

    embedPlyrCnt.add_embed_field(name="Total Online players:", value=str(numberOnline), inline=False)


    #Create world population embed
    embedWorldPop = DiscordEmbed(title="World Population", color="03b2f8")

    embedWorldPop.set_footer(text="Last updated:")
    embedWorldPop.set_timestamp()

    populatedWorlds = getPopulatedWorlds()
    print(populatedWorlds)
    if len(populatedWorlds) > 0:
        for world in populatedWorlds:
            embedWorldPop.add_embed_field(name=world["name"], value=str(world["pop"]))
    else:
        embedWorldPop.add_embed_field(name="No worlds populated", value=":(")

    return (embedPlyrCnt, embedWorldPop)

def getPopulatedWorlds():
    populatedWorlds = []
    for world in worldDict:
        if worldDict[world]["pop"] > 0:
            populatedWorlds.append(worldDict[world])
    return populatedWorlds

def sendMqtt(client):
    jsonToSend = json.dumps(worldDict, indent=1)
    client.publish("playerStatus", payload=jsonToSend, retain=True)

def generateGraphs():
    #Read CSV file into a DataFrame
    try:
        df = pd.read_csv(FILE_DIR + CSV_FILE, names=['timestamp', 'player_count'])
    except Exception as e:
        print("WARNING: Failed to read CSV file.\n     |_" + str(e) + "\n\n")
        return

    #Convert 'timestamp' to a DateTime object and set as index
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df.set_index('timestamp', inplace=True)

    #Calculate the average player count for each hour of an average day
    average_hour_of_day = df.groupby(df.index.hour).mean()

    #Calculate the average player count for each day of an average week
    day_of_week_map = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri', 5: 'Sat', 6: 'Sun'}
    average_day_of_week = df.groupby(df.index.dayofweek).mean()
    average_day_of_week['day_name'] = average_day_of_week.index.map(day_of_week_map)

    #Calculate the overall average player count
    overall_average_player_count = df['player_count'].mean()

    #Get formated current date and time
    formatted_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')

    # Plotting average player count for each hour of an average day with line graph
    plt.figure(figsize=(10, 4))
    plt.plot(average_hour_of_day.index, average_hour_of_day['player_count'], marker='o')
    plt.title('Average Player Count for Each Hour of an Average Day\nlast updated: ' + str(formatted_time) + 'UTC')
    plt.xlabel('Hour of Day (UTC)')
    plt.ylabel('Average Player Count')
    plt.xticks(range(24))
    plt.grid(True)
    plt.savefig(FILE_DIR + DAY_AVG_GRAPH)
    plt.close()

    # Plotting average player count for each day of an average week with line graph
    plt.figure(figsize=(10, 4))
    plt.plot(average_day_of_week['day_name'], average_day_of_week['player_count'], marker='o')
    plt.title('Average Player Count for Each Day of an Average Week\nlast updated: ' + str(formatted_time) + 'UTC')
    plt.xlabel('Day of Week (UTC based)')
    plt.ylabel('Average Player Count')
    plt.grid(True)
    plt.savefig(FILE_DIR + WEEK_AVG_GRAPH)
    plt.close()

    print(f"Overall average: {overall_average_player_count}")


numberOnline = 0


#MQTT 
if MQTT_ENABLE:
    try:
        client = mqtt.Client()
        client.username_pw_set(MQTT_UNAME, password=MQTT_PASS)
        client.connect(MQTT_BROKER_ADDR, MQTT_BROKER_PORT, 60)
        client.loop_start()
    except Exception as e:
        print("WARNING: Failed to connect to MQTT Broker. Disabling MQTT.\n     |_" + str(e) + "\n\n")
        MQTT_ENABLE = False

#Setup the webhooks and send initial message
counter_webhook = DiscordWebhook(url=COUNT_WEBHOOK_URL)
stats_webhook = DiscordWebhook(url=STATS_WEBHOOK_URL, content="stats")

embeds = createEmbeds(numberOnline)

print(embeds[1])
counter_webhook.add_embed(embeds[0])
counter_webhook.add_embed(embeds[1])
counter_webhook.execute()

if AVG_COUNT_ENABLE:
    stats_webhook.execute()

#If the average count feature is enabled, create the directory if it doesnt exist
if AVG_COUNT_ENABLE:
    if not os.path.exists(FILE_DIR):
        os.makedirs(FILE_DIR)


if __name__ == "__main__":

    while True:
        numberOnline = 0
        resetWorldPop(worldDict)
        

        database = mysql.connector.connect(
                host = DATABASE_IP,
                user = DATABASE_USER,
                passwd = DATABASE_PASS,
                database = DATABASE_NAME )

        cursor = database.cursor(dictionary=True)

        #Get all the characters
        cursor.execute("SELECT id, account_id FROM charinfo;")
        characters = cursor.fetchall()
        #print(characters)
        

        #Get timestamp of 24hrs ago
        timestamp = int(time.time()) - (ACTIVITY_AGE * 3600) #convert hrs to sec

        #Get the activity log of the past 24hrs 
        cursor.execute("SELECT character_id, activity, time, map_id FROM activity_log WHERE time > " + str(timestamp) + " ;")
        activityDict = cursor.fetchall()
        #print(activityDict)

        #Cycle through all the characters
        for character in characters:
            #Get character status
            status = getCharStatus(character["id"], activityDict)

            if status["isOnline"]:
                numberOnline += 1

                if status["world"] in worldDict:
                    worldDict[status["world"]]["pop"] += 1
                else:
                    print("\n\nUnknown world ID: " + str(status["world"]) + "\n\n")
                    worldDict["unknown"]["pop"] += 1

        #Append count data to CSV file if enabled
        if AVG_COUNT_ENABLE:
            try:
                with open(FILE_DIR + CSV_FILE, 'a') as f:
                    f.write(f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')},{numberOnline}\n")
            except Exception as e:
                print("WARNING: Failed to write to CSV file.\n     |_" + str(e) + "\n\n")
            

        print("\n\nOnline: " + str(numberOnline))

        time.sleep(.5)
        print("editing")

        if AVG_COUNT_ENABLE:
            generateGraphs()

        try:
            updateDiscord(counter_webhook, stats_webhook)
        except Exception as e:
            print("WARNING: Failed to update Discord. Will try again in " + str(UPDATE_FREQ) + " seconds\n     |_" + str(e) + "\n\n")
            
        if MQTT_ENABLE:
            sendMqtt(client)

        time.sleep(UPDATE_FREQ)



