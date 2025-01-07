from openai import OpenAI
import json
import mysql.connector
from mysql.connector import Error
import time
import logging
import sys
from ASSEMBLY_bot_files.ASSEMBLY_botSettings import GPT_API_KEY, DATABASE_IP, DATABASE_NAME, DATABASE_USER, DATABASE_PASS, NAME_CHECK_FREQ, MAX_NAMES, LOG_TO_FILE, LOG_FILE, DEBUG, FULL_NAME_APPROVAL_GPT_SYSTEM_MESSAGE, TRACK_OFFENSES

MODULE_NAME = "[NameApproval]"

#------------------------------------------------------------------------------------------
# Helper Functions
#------------------------------------------------------------------------------------------

def check_DB_connection(connection):
    """
    Check and ensure the MySQL database connection is active, and attempt to reconnect if it is lost.

    Args:
        connection (object): A MySQL database connection object.

    Returns:
        bool: True if the connection is active or successfully reconnected, False otherwise.
    """
    try:
        if not connection.is_connected():
            print(MODULE_NAME + ": Lost connection to MySQL DB, attempting to reconnect...")
            connection.reconnect(attempts=3, delay=5)

            #Check if the connection was re-established
            if connection.is_connected():
                print(MODULE_NAME + ": Reconnected to MySQL DB")
                return True
            else:
                print(MODULE_NAME + ": Failed to reconnect to MySQL DB")
        else:
            print(MODULE_NAME + ": Connection to MySQL DB still active")
            return True
    except Error as e:
        print(f"{MODULE_NAME}: The error '{e}' occurred while reconnecting")
        
    return False


def pull_char_names(connection):
    """
    Retrieve pending character names from the database.

    Args:
        connection (object): A MySQL database connection object.
    
    Returns:
        list[str]: A list of strings containing pending character names, or None if the 
              database connection is invalid.
              Ex = ['JohnDoe', 'JaneDoe', 'Player123']
    """
    if not check_DB_connection(connection):
        print(MODULE_NAME + ": No mysql connection, unable to check for character names")
        return None
    
    cursor = connection.cursor()
    cursor.execute("SELECT pending_name FROM charinfo WHERE pending_name <> '' AND needs_rename='0';")
    result = cursor.fetchall()

    # Convert the list of tuples to a list of names
    result = [name[0] for name in result]

    return result


def pull_pet_names(connection):
    """
    Retrieve approved pet names from the database.

    Args:
        connection (object): A MySQL database connection object.
    
    Returns:
        list[str]: A list of strings containing approved pet names, or None if the 
              database connection is invalid.
              Ex = ['Fluffy', 'Buddy', 'Max']

    """
    if not check_DB_connection(connection):
        print(MODULE_NAME + ": No mysql connection, unable to check for pet names")
        return None
    
    cursor = connection.cursor()
    cursor.execute("SELECT pet_name FROM pet_names WHERE approved='1'")
    result = cursor.fetchall()

    # Convert the list of tuples to a list of names
    result = [name[0] for name in result]

    return result


def make_GPT_request(client, nameList):
    """
    Evaluate a list of names using the GPT model and retrieve names to reject.

    Args:
        client (object): OpenAI API client for making requests.
        nameList (list[str]): List of names to evaluate.

    Returns:
        list[dict]: Names flagged for rejection with reasons, or None on failure.
        Example: [{"name": "JohnDoe", "reason": "Inappropriate"}, {"name": "JaneDoe", "reason": "Offensive"}]
    """
    if not nameList:
        return None
    
    if len(nameList) == 0:
        return None
    
    # Convert the list of names to a JSON string
    user_message = json.dumps({"names": nameList})

    if DEBUG:
        print("Checking names: " + user_message)

    # Make the request to OpenAI
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": FULL_NAME_APPROVAL_GPT_SYSTEM_MESSAGE},
                {"role": "user", "content": user_message}
            ],
            temperature=.5,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )
    except Exception as e:
        print(MODULE_NAME + ": Failed to make request to OpenAI \n Error: " + str(e))
        return None
    
    if response.choices[0].message.content and DEBUG:
        print(MODULE_NAME + ": Raw GPT resonse: " + response.choices[0].message.content + "\n\n")  

    # Convert the JSON response to a dictionary
    try:
        namesToReject = json.loads(response.choices[0].message.content)
    except Exception as e:
        print(MODULE_NAME + ": Faild to convert GPT resonse to JSON\nError: " + str(e))
        namesToReject = None

    return namesToReject


def check_names(openAIClient, nameList):
    """
    Check a list of names for approval using an OpenAI client.

    Args:
        openAIClient (object): An instance of the OpenAI client used to process name checks.
        nameList (list[str]): A list of names to be checked for approval.

    Returns:
        dict: A dictionary containing:
            - "namesToReject" (list[dict]): Names flagged for rejection with reasons.
                    Example: [{"name": "JohnDoe", "reason": "Inappropriate"}, {"name": "JaneDoe", "reason": "Offensive"}]
            - "totalNumOfNames" (int): The total number of names processed.
        Returns None if the input nameList is empty or invalid.
    """
    totalNamesToReject = []

    if nameList and len(nameList) > 0:
        numOfNames = len(nameList)

        '''
        Split the list of names into sublists of MAX_NAMES length
        This is done to limit on the number of names that can be checked at once
        '''
        nameList = [nameList[i:i + MAX_NAMES] for i in range(0, len(nameList), MAX_NAMES)]
        
        # Check each sublist of names
        for list in nameList:
            namesToReject = make_GPT_request(openAIClient, list)

            if namesToReject and len(namesToReject) > 0:
                totalNamesToReject = totalNamesToReject + namesToReject

        return {"namesToReject": totalNamesToReject, "totalNumOfNames": numOfNames}

    return None


def log_names_checked_and_rejected(name_logger, rejectedNames, totalNames):
    """
    Log the names that were checked and rejected during the approval process.

    Args:
        name_logger (object): A logger object
        rejectedNames (dict): A dictionary containing:
            - "namesToReject" (list[dict]): Names flagged for rejection with reasons.
                    Example: [{"name": "JohnDoe", "reason": "Inappropriate"}, {"name": "JaneDoe", "reason": "Offensive"}]
            - "totalNumOfNames" (int): The total number of names processed.
        totalNames (list[str]): A list of strings containing all names that were checked.
                                  Example: ["Name1", "Name2", "Name3"]

    Returns:
        None: This function does not return any value. It logs the information instead.
    """
    try:
        # Log the names checked
        if totalNames and len(totalNames) > 0:
            # Extract names from the tuples and convert to a comma-separated string
            total_names_str = ", ".join([name for name in totalNames])
            name_logger.info(f"Names checked: \n {total_names_str}\n\n")
        else:
            name_logger.info("No names checked this round")
        
        # Log the names rejected
        if rejectedNames and len(rejectedNames["namesToReject"]) > 0:
            rejected_names_str = json.dumps(rejectedNames["namesToReject"], indent=4)
            name_logger.info(f"Names rejected:\n {rejected_names_str}\n\n")
        else:
            name_logger.info("No names rejected this round")
    except Exception as e:
        print("Failed to log names checked and/or rejected.\nError: " + str(e))


def report_offenses(connection, rejectedNames, name_type):
    """
    Determines who submited the flagged name and logs the offense to the user's report.

    Args:
        connection (object): A MySQL database connection object.
        rejectedNames (list[dict]): Names flagged for rejection with reasons.
                    Example: [{"name": "JohnDoe", "reason": "Inappropriate"}, {"name": "JaneDoe", "reason": "Offensive"}]
        name_type (str): The type of name being checked (e.g. "character" or "pet")

    Returns:
        N/A - This function does not return any value.
    """
    # Check DB connection
    if not check_DB_connection(connection):
        print(MODULE_NAME + ": No mysql connection, unable to report offenses")
        return
    
    cursor = connection.cursor()

    # Iterate through the rejected names
    for rejected in rejectedNames:
        name = rejected.get("name")
        reason = rejected.get("reason")

        # Get the account who submitted the name
        if name_type == "character":
            cursor.execute("SELECT account_id FROM charinfo WHERE pending_name = %s", (name,))
            result = cursor.fetchone()
            account_id = result[0] if result else None  # Get value from tuple

        elif name_type == "pet":
            cursor.execute("SELECT owner_id FROM pet_names WHERE pet_name = %s", (name,))
            result = cursor.fetchone()
            owner_id = result[0] if result else None  # Get value from tuple

            if owner_id:
                # Get the account id from the owner id
                cursor.execute("SELECT account_id FROM charinfo WHERE id = %s", (owner_id,))
                result = cursor.fetchone()
                account_id = result[0] if result else None
            else:
                print(MODULE_NAME + ": Failed to find owner id for pet name: " + name)
                account_id = None

        else:
            print(MODULE_NAME + ": Invalid name type: " + name_type)
            account_id = None

        if account_id:
            # Get key id from account id
            cursor.execute("SELECT play_key_id FROM accounts WHERE id = %s", (account_id,))
            result = cursor.fetchone()
            key_id = result[0] if result else None  # Get value from tuple

            if key_id:
                # Create an offense object
                offense_obj = {
                    "timestamp": int(time.time()),
                    "type": f"{name_type} name",
                    "offense": f"Submitted name: `{name}` was flagged for: {reason}",
                    "action-taken": "Name rejected",
                    "mod-notified": False
                }

                # Fetch the user's record
                cursor.execute('SELECT notes FROM play_keys WHERE id=%s', (key_id,))
                result = cursor.fetchone()

                # If there is no result
                if not result:
                    print(MODULE_NAME + ": Failed to find user record for key ID: " + key_id)
                    return
                
                # If there is no user record, create one
                if not result[0]:
                    user_record = {
                            "notes":[],
                            "offenses":[],
                            "warnings":[]
                        }
                else:
                    user_record = json.loads(result[0])

                # Add the offense to the user's record
                user_record["offenses"].append(offense_obj)

                cursor.execute('UPDATE play_keys SET notes=%s WHERE id=%s', (json.dumps(user_record), key_id))
                connection.commit()

            else:
                print(MODULE_NAME + ": Failed to find key id for account ID: " + account_id)
        else:
            print(MODULE_NAME + ": Failed to find user who submitted the name: " + name)


#------------------------------------------------------------------------------------------
# Main Function
#------------------------------------------------------------------------------------------
def main():
    global LOG_TO_FILE

    totalNamesToReject = {}

    print(MODULE_NAME + ": Starting up...")

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

    openAIClient = OpenAI(api_key=GPT_API_KEY)

    while(True):
        print(MODULE_NAME + ": Starting name check...")

        if LOG_FILE:
            name_logger.info("\n\n********************************\n********* STARTING NAME CHECK\n********************************\n")

        # Connect to the database
        print(MODULE_NAME + ": Connecting to MySQL DB...")
        connection = None
        try:
            connection = mysql.connector.connect(
                host = DATABASE_IP,
                user = DATABASE_USER,
                password = DATABASE_PASS,
                database = DATABASE_NAME
            )
            print(MODULE_NAME + ": Connection to MySQL DB successful")
        except Error as e:
            print(f"{MODULE_NAME}: The error '{e}' occurred")

        namesChecked = False

        # Pull names from the database
        charNames = pull_char_names(connection)
        petNames = pull_pet_names(connection)

        #---------------------------------------------------------------------
        # Check character names
        #---------------------------------------------------------------------
        print(MODULE_NAME + ": Checking character names...")
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
                print(MODULE_NAME + ": Checked " + str(totalNamesToReject["totalNumOfNames"]) + " character names and rejected " + str(len(totalNamesToReject["namesToReject"])) + " names")
            
                if TRACK_OFFENSES:
                    report_offenses(connection, totalNamesToReject["namesToReject"], "character")

            else:
                print(MODULE_NAME + ": No mysql connection, unable to moderate character names")
        
        else:
            print(MODULE_NAME + ": No character names to approve, skipping...")

        # Log the names checked and rejected
        if LOG_TO_FILE:
            log_names_checked_and_rejected(name_logger, totalNamesToReject, charNames)


        #---------------------------------------------------------------------
        # Check pet names
        #---------------------------------------------------------------------
        print(MODULE_NAME + ": Checking pet names...")
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
                print(MODULE_NAME + ": Checked " + str(totalNamesToReject["totalNumOfNames"]) + " character names and rejected " + str(len(totalNamesToReject["namesToReject"])) + " names")
            
                if TRACK_OFFENSES:
                    report_offenses(connection, totalNamesToReject["namesToReject"], "pet")

            else:
                print(MODULE_NAME + ": No mysql connection, unable to moderate pet names")
        
        else:
            print(MODULE_NAME + ": No pet names to approve, skipping...")

        # Log the names checked and rejected
        if LOG_TO_FILE:
            log_names_checked_and_rejected(name_logger, totalNamesToReject, petNames)

        if not namesChecked:
            print(MODULE_NAME + ": No names to check this round")

        # Close the database connection
        connection.close()

        if LOG_FILE:
            name_logger.info("\n\n********************************\n********* ^^ END NAME CHECK ^^\n********************************\n")

        # Sleep for a set amount of time
        print(MODULE_NAME + ": Sleeping for " + str(NAME_CHECK_FREQ) + " seconds...")
        time.sleep(NAME_CHECK_FREQ)
        

if __name__ == "__main__":
    print(MODULE_NAME + ": Please run ASSEMBLY_bot.py to start")
    sys.exit(1)