import mysql.connector
from charXmlPullerSettings import *
import re
import subprocess
import os


printDebug = False
characterList = []

####################################################################################################
#                                       FUNCTIONS                                                  #
####################################################################################################

#Checks the format of the account key
def check_format(s):
    pattern = r'^[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}$'
    return bool(re.match(pattern, s))



####################################################################################################
#                                       MAIN FUNCTION                                              #
####################################################################################################

# Get home directory path
homeDir = os.getenv('HOME')

if printDebug:
    print("Home directory: " + homeDir)

# Create directory for xmls in the home directory
try:
    os.mkdir(homeDir + "/xmls")
except:
    pass

# Connect to database
try:
    db = mysql.connector.connect(
        host=DATABASE_IP,
        user=DATABASE_USER,
        passwd=DATABASE_PASS,
        database=DATABASE_NAME
    )
except mysql.connector.Error as err:
    print(err)
    print("Failed to connect to database. Exiting.")
    exit()

cursor = db.cursor(dictionary=True)

# Gather account key from user
while True:
    accountKey = input("Enter account key: ")

    if not check_format(accountKey):
        print("Invalid account key format. Please try again.\n")
    else:
        break

# Ask user if they want the xmls cleaned
while True:
    cleanXmls = input("Clean XMLs? (Y/N): ")

    if cleanXmls.lower() == "y":
        cleanXmls = True
        break
    elif cleanXmls.lower() == "n":
        cleanXmls = False
        break
    else:
        print("Invalid input. Please try again.\n")
        
# Get key id from database
cursor.execute("SELECT id FROM play_keys WHERE key_string = %s", (accountKey,))
keyIdDict = cursor.fetchall()

keyId = keyIdDict[0]["id"]

if printDebug:
    print("Key ID: " + str(keyId))

# Get account id from database
cursor.execute("SELECT id FROM accounts WHERE play_key_id = %s", (keyId,))
accountIdDict = cursor.fetchall()

accountId = accountIdDict[0]["id"]

if printDebug:
    print("Account ID: " + str(accountId))

# Get account name from database
cursor.execute("SELECT name FROM accounts WHERE play_key_id = %s", (keyId,))
accountNameDict = cursor.fetchall()

accountName = accountNameDict[0]["name"]

if printDebug:
    print("Account Name: " + accountName)


# Print account name   
print("\nAccount Name: " + accountName)

# Get character ids from database
cursor.execute("SELECT * FROM charinfo WHERE account_id = %s", (accountId,))
characterIdDict = cursor.fetchall()

# Print number of characters account has
print("Number of Characters: " + str(len(characterIdDict)) + "\n")

# Exit if the account has no characters
if len(characterIdDict) == 0:
    print("Account has no characters. Exiting.")
    exit()

# Ask user for the new account ID if they want the xmls cleaned
if cleanXmls:
    while True:
        newAccountId = input("Enter new account ID: ")

        if not newAccountId.isdigit():
            print("Invalid account ID format. Please try again.\n")
        else:
            break

# Cycle through character ids
for character in characterIdDict:

    # Get character name from database
    characterName = character["name"]

    # Add name to character list
    characterList.append(characterName)

    if printDebug:
        print("Character Name: " + characterName)
    
    # Get character id from database
    characterId = character["id"]

    if printDebug:
        print("Character ID: " + str(characterId))

    # Get character xml from database
    cursor.execute("SELECT xml_data FROM charxml WHERE id = %s", (characterId,))
    characterXmlDict = cursor.fetchall()

    # Write character xml to file
    characterXml = characterXmlDict[0]["xml_data"]

    if printDebug:
        print("Character XML: " + characterXml)

    with open(homeDir + "/xmls/" + characterName + ".xml", "w") as xmlFile:
        xmlFile.write(characterXml)

    # Clean xml if requested
    if cleanXmls:
        # Run the xmlClean.py script
        subprocess.run(["python3", "xmlClean.py", homeDir + "/xmls/" + characterName + ".xml", newAccountId])

# Print character list
print("\nCharacter List:")
for character in characterList:
    print(character)
