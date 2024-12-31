import os
from openai import OpenAI
import json
import mysql.connector
from mysql.connector import Error
import time
import logging
from datetime import datetime
from nameApprovalSettings import *

#------------------------------------------------------------------------------------------
# Helper Functions
#------------------------------------------------------------------------------------------

# Set up database connection
def create_mysql_connection():
    connection = None
    try:
        connection = mysql.connector.connect(
            host = DATABASE_IP,
            user = DATABASE_USER,
            password = DATABASE_PASS,
            database = DATABASE_NAME
        )
        print("Connection to MySQL DB successful")
    except Error as e:
        print(f"The error '{e}' occurred")
    return connection


def check_DB_connection(connection):
    try:
        if not connection.is_connected():
            print("Lost connection to MySQL DB, attempting to reconnect...")
            connection.reconnect(attempts=3, delay=5)

            #Check if the connection was re-established
            if connection.is_connected():
                print("Reconnected to MySQL DB")
                return True
            else:
                print("Failed to reconnect to MySQL DB")
        else:
            print("Connection to MySQL DB still active")
            return True
    except Error as e:
        print(f"The error '{e}' occurred while reconnecting")
        
    return False


def pull_char_names(connection):
    if not check_DB_connection(connection):
        print("No mysql connection, unable to check for character names")
        return None
    
    cursor = connection.cursor()
    cursor.execute("SELECT pending_name FROM charinfo WHERE pending_name <> '' AND needs_rename='0';")
    result = cursor.fetchall()

    return result


def pull_pet_names(connection):
    if not check_DB_connection(connection):
        print("No mysql connection, unable to check for pet names")
        return None
    
    cursor = connection.cursor()
    cursor.execute("SELECT pet_name FROM pet_names WHERE approved='1'")
    result = cursor.fetchall()

    return result


def split_list(strings):
    """
    Splits a list of strings into sublists, each with a maximum length of max_size.
    """
    return [strings[i:i + MAX_NAMES] for i in range(0, len(strings), MAX_NAMES)]


def make_GPT_request(client, nameList):
    if not nameList:
        return None
    
    if len(nameList) == 0:
        return None
    
    # Create the user message
    user_message = json.dumps({"names": nameList})

    if DEBUG:
        print("Checking names: " + user_message)

    # Make the request to OpenAI
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": FULL_SYSTEM_MESSAGE},
                {"role": "user", "content": user_message}
            ],
            temperature=.5,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )
    except Exception as e:
        print("Failed to make request to OpenAI \n Error: " + str(e))
        return None
    
    if response.choices[0].message.content and DEBUG:
        print("Raw GPT resonse: " + response.choices[0].message.content + "\n\n")  

    # Convert the response to JSON
    try:
        namesToReject = json.loads(response.choices[0].message.content)
    except Exception as e:
        print("Faild to convert GPT resonse to JSON\nError: " + str(e))
        namesToReject = None

    return namesToReject


def check_names(openAIClient, nameList):
    totalNamesToReject = []

    if nameList and len(nameList) > 0:
        numOfNames = len(nameList)

        nameList = split_list(nameList)

        for list in nameList:
            namesToReject = make_GPT_request(openAIClient, list)

            if namesToReject and len(namesToReject) > 0:
                totalNamesToReject = totalNamesToReject + namesToReject

        return {"namesToReject": totalNamesToReject, "totalNumOfNames": numOfNames}

    return None


def log_names_checked_and_rejected(rejectedNames, totalNames):
    try:
        # Log the names checked
        if totalNames and len(totalNames) > 0:
            # Extract names from the tuples and convert to a comma-separated string
            total_names_str = ", ".join([name[0] for name in totalNames])
            name_logger.info(f"Names checked: \n {total_names_str}\n\n")
        else:
            name_logger.info("No names checked this round")
        
        # Log the names rejected
        if rejectedNames and len(rejectedNames["namesToReject"]) > 0:
            rejected_names_with_reasons = [{"name": entry["name"], "reason": entry["reason"]} for entry in rejectedNames["namesToReject"]]
            rejected_names_str = json.dumps(rejected_names_with_reasons, indent=4)
            name_logger.info(f"Names rejected:\n {rejected_names_str}\n\n")
        else:
            name_logger.info("No names rejected this round")
    except Exception as e:
        print("Failed to log names checked and/or rejected.\nError: " + str(e))


#------------------------------------------------------------------------------------------
# Main Function
#------------------------------------------------------------------------------------------
if __name__ == "__main__":

    totalNamesToReject = {}

    print("Starting up...")

    # Setup logging
    if LOG_TO_FILE:
        # Set up logging for name-related information
        try:
            name_logger = logging.getLogger('name_logger')
            name_logger.setLevel(logging.INFO)
            handler = logging.FileHandler(LOG_FILE)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            name_logger.addHandler(handler)
        except Exception as e:
            print("Failed to set up logging for name checks. Disabling logging\nError: " + str(e))
            LOG_TO_FILE = False

    openAIClient = OpenAI(api_key=API_KEY)

    while(True):
        print("Starting name check...")

        if LOG_FILE:
            name_logger.info("\n\n********************************\n********* STARTING NAME CHECK\n********************************\n")

        # Connect to the database
        print("Connecting to MySQL DB...")
        connection = create_mysql_connection()

        namesChecked = False

        # Pull names from the database
        charNames = pull_char_names(connection)
        petNames = pull_pet_names(connection)

        #---------------------------------------------------------------------
        # Check character names
        #---------------------------------------------------------------------
        print("Checking character names...")
        totalNamesToReject = check_names(openAIClient, charNames)
        
        if totalNamesToReject:
            
            # Ensure we have a database connection
            if check_DB_connection(connection):

                cursor = connection.cursor()

                # Check if there are any names to reject
                if len(totalNamesToReject["namesToReject"]) > 0:
                    
                    # Reject the names
                    names_to_reject = ["'" + entry["name"] + "'" for entry in totalNamesToReject["namesToReject"]]
                    cursor.execute("UPDATE charinfo SET needs_rename='1' WHERE pending_name IN (" + ", ".join(names_to_reject) + ");")
                    
                #Approve remaining names
                cursor.execute("UPDATE charinfo SET name = pending_name WHERE pending_name != '' AND needs_rename = '0';") #Set the name to the pending name
                cursor.execute("UPDATE charinfo SET pending_name = '' WHERE pending_name != '' AND needs_rename = '0';") #Clear the pending name
                
                # Commit the changes
                connection.commit()

                namesChecked = True
                print("Checked " + str(totalNamesToReject["totalNumOfNames"]) + " character names and rejected " + str(len(totalNamesToReject["namesToReject"])) + " names")
            
            else:
                print("No mysql connection, unable to moderate character names")
        
        else:
            print("No character names to approve, skipping...")

        # Log the names checked and rejected
        if LOG_TO_FILE:
            log_names_checked_and_rejected(totalNamesToReject, charNames)


        #---------------------------------------------------------------------
        # Check pet names
        #---------------------------------------------------------------------
        print("Checking pet names...")
        totalNamesToReject = check_names(openAIClient, petNames)

        if totalNamesToReject:
            
            # Ensure we have a database connection
            if check_DB_connection(connection):

                cursor = connection.cursor()

                # Check if there are any names to reject
                if len(totalNamesToReject["namesToReject"]) > 0:
                    
                    # Reject the names
                    names_to_reject = ["'" + entry["name"] + "'" for entry in totalNamesToReject["namesToReject"]]
                    cursor.execute("UPDATE pet_names SET approved ='0' WHERE pet_name IN (" + ", ".join(names_to_reject) + ");")
                    
                #Approve remaining names
                cursor.execute("UPDATE pet_names SET approved = '2' WHERE approved != '0';") 

                # Commit the changes
                connection.commit()

                namesChecked = True
                print("Checked " + str(totalNamesToReject["totalNumOfNames"]) + " character names and rejected " + str(len(totalNamesToReject["namesToReject"])) + " names")
            
            else:
                print("No mysql connection, unable to moderate pet names")
        
        else:
            print("No pet names to approve, skipping...")

        # Log the names checked and rejected
        if LOG_TO_FILE:
            log_names_checked_and_rejected(totalNamesToReject, petNames)

        if not namesChecked:
            print("No names to check this round")

        # Close the database connection
        connection.close()

        if LOG_FILE:
            name_logger.info("\n\n********************************\n********* ^^ END NAME CHECK ^^\n********************************\n")

        # Sleep for a set amount of time
        print("Sleeping for " + str(NAME_CHECK_FREQ) + " seconds...")
        time.sleep(NAME_CHECK_FREQ)
        