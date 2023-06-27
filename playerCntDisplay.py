import mysql.connector
import paho.mqtt.client as mqtt
from discord_webhook import DiscordWebhook, DiscordEmbed #https://github.com/lovvskillz/python-discord-webhook
import json
import time
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

def updateDiscord(webhook, sentWebhook):
    webhook.remove_embeds()
    
    embeds = createEmbeds(numberOnline)

    webhook.add_embed(embeds[0])
    webhook.add_embed(embeds[1])

    sentWebhook = webhook.edit(sentWebhook)

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

#Setup the webhook and send initial message
webhook = DiscordWebhook(url=WEBHOOK_URL)

embeds = createEmbeds(numberOnline)

print(embeds[1])
webhook.add_embed(embeds[0])
webhook.add_embed(embeds[1])
sentWebhook = webhook.execute()

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

    
    print("\n\nOnline: " + str(numberOnline))

    time.sleep(.5)
    print("editing")

    try:
        updateDiscord(webhook, sentWebhook)
    except Exception as e:
         print("WARNING: Failed to update Discord. Will try again in " + str(UPDATE_FREQ) + " seconds\n     |_" + str(e) + "\n\n")
        
    if MQTT_ENABLE:
        sendMqtt(client)

    time.sleep(UPDATE_FREQ)



