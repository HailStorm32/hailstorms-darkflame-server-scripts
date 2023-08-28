import mysql.connector
from contrabandCheckSettings import *
import xmltodict
from pprint import pprint
from copy import deepcopy

printDebug = False

flaggedAccounts = []

# flaggedAccounts = [
#     {
#         "keyid": "ABC123",
#         "flaggedCharacters": [
#             {
#                 "characterName": "test",
#                 "contraband": [
#                     {
#                        "itemID": 1,
#                        "name": "test"
#                     }
#                 ]
#             }
#         ]
#     } 
# ]


# xml -> dict items layout
# 'items': {
#   'in': [
#     {
#       '@t': '0',
#       'i': [
#         {'@l': '12754', '@id': '1152921508911832649', '@s': '10', '@c': '1', '@b': 'true', '@eq': 'false', '@sk': '0', '@parent': '0'},
#         {'@l': '14173', '@id': '1152921508912718858', '@s': '12', '@c': '1', '@b': 'true', '@eq': 'false', '@sk': '0', '@parent': '0'},
#         # ... (and so on for other 'i' elements under 'in' with '@t': '0')
#       ]
#     },
#     {
#       '@t': '1',
#       'i': [
#         {'@l': '7850', '@id': '1152921508913342801', '@s': '8', '@c': '1', '@b': 'true', '@eq': 'false', '@sk': '0', '@parent': '0'},
#         {'@l': '6792', '@id': '1152921508949624505', '@s': '66', '@c': '1', '@b': 'true', '@eq': 'false', '@sk': '0', '@parent': '0'},
#         # ... (and so on for other 'i' elements under 'in' with '@t': '1')
#       ]
#     },
#     {
#       '@t': '4',
#       'i': None
#     },
#     # ... (and so on for other 'in' elements)
#   ]
# }



# TODO:
#   - Have option to remove contraband items from xmls  
#   - Have option to send ingame mail to user with contraband items

####################################################################################################
#                                       FUNCTIONS                                                  #
####################################################################################################
def matchContraband(inventoryItem):
    contrabandFound = {}

    # Cycle through contraband items
    for contrabandItem in contrabandIds:     

        # Check if the item is contraband
        if inventoryItem == str(contrabandItem["id"]):
            
            if printDebug:
                print("\nFound contraband item: " + contrabandItem["name"])

            # Create an entry for the contraband list
            contrabandFound.update({
                "itemID": contrabandItem["id"],
                "name": contrabandItem["name"]
            })

    return contrabandFound


def getContraband(xml, charId):
    contrabandFoundList = []

    # Convert xml to dictionary
    try:
        xmlDict = xmltodict.parse(xml)
    except:
        print(f"\n\nWARNING: Posible corrupt charxml for char_id: {charId}. Skipping...\n\n")
        return contrabandFoundList

    # Cycle through invenotry types
    for inventoryType in xmlDict["obj"]["inv"]["items"]["in"]:
        
        # Skip new characters with no inventory
        if len(xmlDict["obj"]["inv"]["items"]["in"]) <= 2:
            if printDebug:
                print("\nSkipping new character with no inventory.")
            continue
        
        # Check if the inventory type is one we want to search
        if any(str(item['id']) == inventoryType["@t"] and item['search'] for item in inventoryTypes):

            # Skip empty inventory types
            if len(inventoryType) <= 1:
                continue

            #If the inventory only has one item, it will be a dictionary instead of a list
            if type(inventoryType["i"]) is dict: 

                # Check if the item is contraband
                contrabandFound = matchContraband(inventoryType["i"]["@l"])

                if contrabandFound:
                    contrabandFoundList.append(contrabandFound)
            
            # If the inventory has multiple items, it will be a list
            else:
                # Cycle through inventory items
                for inventoryItem in inventoryType["i"]:

                    # Check if the item is contraband
                    contrabandFound = matchContraband(inventoryItem["@l"])

                    if contrabandFound:
                        contrabandFoundList.append(contrabandFound)

                    

    return contrabandFoundList
                    
     



####################################################################################################
#                                       MAIN FUNCTION                                              #
####################################################################################################

# Connect to database
try:
    db = mysql.connector.connect(
        host=DATABASE_IP,
        user=DATABASE_USER,
        passwd=DATABASE_PASS,
        database=DATABASE_NAME
    )
except:
    print("Failed to connect to database. Exiting.")
    exit()

cursor = db.cursor(dictionary=True)

# Get all characters ids
cursor.execute("SELECT id FROM accounts")
accountIds = cursor.fetchall()

currentAccount = 0

# Cycle through all account ids
for accountId in accountIds:
    accountInfo = {}
    characterInfo = {}

    print(f'\rSearching account {currentAccount + 1} of {len(accountIds)}', end='', flush=True)
    currentAccount += 1

    # Skip exempt accounts
    if accountId["id"] in exemptAccountIds:
        continue

    # Get the account key id
    cursor.execute("SELECT play_key_id FROM accounts WHERE id = %s", (accountId["id"],))
    keyIdDict = cursor.fetchall()

    keyId = keyIdDict[0]["play_key_id"]

    # Skip the admin account
    if keyId == 0:
        continue

    # Get the account key
    cursor.execute("SELECT key_string FROM play_keys WHERE id = %s", (keyId,))
    keyDict = cursor.fetchall()

    accountInfo["keyid"] = keyDict[0]["key_string"]

    if printDebug:
        print("\nKey: " + str(characterInfo["keyid"]))

    # Get all characters for the account
    cursor.execute("SELECT id, name FROM charinfo WHERE account_id = %s", (accountId["id"],))
    characters = cursor.fetchall()

    accountInfo["flaggedCharacters"] = []

    # Cycle through all characters
    for character in characters:
        # Get the character name
        characterInfo["characterName"] = character["name"]

        if printDebug:
            print("\nCharacter Name: " + characterInfo["characterName"])

        # Get the character id
        characterId = character["id"]

        # Get the character's xml
        cursor.execute("SELECT xml_data FROM charxml WHERE id = %s", (characterId,))
        xmlDict = cursor.fetchall()

        xml = xmlDict[0]["xml_data"]

        # Get the character's contraband
        contraband = getContraband(xml, characterId)

        # Check if the character has contraband
        if contraband:
            # Add the contraband to the character info
            characterInfo["contraband"] = contraband

            # Add the character to the account info
            accountInfo["flaggedCharacters"].append(deepcopy(characterInfo))

    if accountInfo["flaggedCharacters"]:
        flaggedAccounts.append(deepcopy(accountInfo))

# Print a blank line
print()

# Print the flagged characters
if flaggedAccounts:
    
    print("\n\nFlagged Accounts:")
    print('-' * 40)  # print separator line

    for account in flaggedAccounts:
        print(f"Key ID: {account['keyid']}")
        
        flagged_chars = account.get('flaggedCharacters', [])
        
        for char in flagged_chars:
            print(f"\tCharacter Name: {char['characterName']}")
            
            contraband_list = char.get('contraband', [])
            
            if contraband_list:
                print("\t\tContraband List:")
                
                for contraband in contraband_list:
                    print(f"\t\t\tItem ID: {contraband['itemID']}, Name: {contraband['name']}")
            else:
                print("\t\tNo Contraband.")
                
        print('-' * 40)  # print separator line
else:
    print("No flagged accounts found.")