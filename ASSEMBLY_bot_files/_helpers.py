import json
import random
import re
import requests
import string
from datetime import datetime
from ASSEMBLY_bot_files.ASSEMBLY_botSettings import WHITELIST_GPT_SYSTEM_MESSAGE, DEBUG

class RecordTypes:
    """
    Enum for note types
    """
    def __init__(self):       
        self.NOTE = 0
        self.OFFENSE = 1
        self.WARNING = 2

        self.ALL = 999
class BotHelpers():
    """
    A mixin containing helper/utility functions, including DB logic.
    Expects that the final subclass sets 'self.mysql_connector'.
    """
    def __init__(self):
        self.record_type = RecordTypes()

    ####################################################################################################
    # Helper Methods
    ####################################################################################################

    def _get_db_connection(self):
        """
        Get a database connection from the connection pool.

        Parameters:
            None

        Returns:
            connection (MySQLConnection or None): A MySQL connection object if successful, 
                              or None if the connection fails.
        """
        try:
            connection = self._connection_pool.get_connection()
            if connection.is_connected():
                return connection
        except Exception as e:
            print(f"{self._MODULE_NAME}: ERROR: Failed to get DB connection from pool: {e}")
            return None

    def _lock_account(self, member_name, uuid, player_left=True):
        """
        Locks or deactivates a user's account or play key based on their activity and server status.

        Parameters:
            member_name (str): The name of the member whose account or play key is being locked or deactivated.
            uuid (str): The unique identifier (UUID) of the user in the database.
            player_left (bool): Indicates whether the user has left the server. Defaults to True.

        Returns:
            botMessageChannelMessage (str): A message indicating the result of the operation, such as whether 
                            the account was locked, the play key was deactivated, or no play key was found.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            return f'⚠️ Unable to lock account of user `{member_name}`. No DB connection'

        #Get the play key for the user and the number of times it has been used
        cursor = db_connection.cursor()
        cursor.execute('SELECT key_string,times_used,id FROM play_keys WHERE discord_uuid=%s', (str(uuid),))
        result = cursor.fetchone()
        
        #If the user has a play key
        if result:
            key = result[0]
            key_uses = result[1]
            key_id = result[2]

            #Only lock account if the key has been used
            if key_uses > 0:
                #Lock the account
                cursor.execute('UPDATE accounts SET locked=1 WHERE play_key_id=%s', (key_id,))
                db_connection.commit()
                cursor.close()

                if player_left:
                    botMessageChannelMessage = f'The user `{member_name}` has left the server. **Their account has been locked.**\nTheir play key was: `{key}`'

                    note_message = f'Account locked on leave. Date: {datetime.now()}'
                else:
                    botMessageChannelMessage = f'Account has been locked for user `{member_name}`.'

                    note_message = f'Account locked by mythran. Date: {datetime.now()}'
            
            #If the key has not been used, deactivate it
            else:
                cursor.execute('UPDATE play_keys SET active=0 WHERE key_string=%s', (str(key),))
                db_connection.commit()

                if player_left:
                    botMessageChannelMessage = f'The user `{member_name}` has left the server. Play key found, but no account. \n **Key has been deactivated.**\nTheir play key was: `{key}`'

                    note_message = f'Playkey deactivated on leave. Date: {datetime.now()}'
                else:
                    botMessageChannelMessage = f'Playkey for user `{member_name}` has been deactivated. No account found.'

                    note_message = f'Playkey deactivated by mythran. Date: {datetime.now()}'
            
            #Save a note for the user that their account/key was locked
            self._save_record_entry(str(uuid), self.record_type.NOTE, note_message)

        #If the user does not have a play key
        else:
            if player_left:
                botMessageChannelMessage = f'The user `{member_name}` has left the server. **No play key found for them.**'
            else:
                botMessageChannelMessage = f'The user `{member_name}` does not have a playkey'

        db_connection.close()

        return botMessageChannelMessage 


    def _unlock_account(self, member_name, uuid):
        '''
        Unlocks a user's account or reactivates their play key based on the provided UUID.

        Parameters:
            member_name (str): The name of the member whose account or play key is to be unlocked/reactivated.
            uuid (str): The unique identifier of the user in the database.

        Returns:
            botMessageChannelMessage (str): A message indicating the result of the unlock/reactivation process.
        '''
        db_connection = self._get_db_connection()

        if not db_connection:
            return f'⚠️ Unable to unlock account of user `{member_name}`. No DB connection'

        # Get the play key for the user
        cursor = db_connection.cursor()
        cursor.execute('SELECT key_string, times_used, id FROM play_keys WHERE discord_uuid=%s', (str(uuid),))
        result = cursor.fetchone()
        
        # If the user has a play key
        if result:
            key = result[0]
            key_uses = result[1]
            key_id = result[2]

            #Only unlock account if the key has been used
            if key_uses > 0:
                # Unlock the account if it was previously locked
                cursor.execute('UPDATE accounts SET locked=0 WHERE play_key_id=%s', (key_id,))
                db_connection.commit()

                botMessageChannelMessage = f'Account unlocked for user `{member_name}`.'

                note_message = f'Account unlocked by mythran. Date: {datetime.now()}'

            # Reactivate the play key if it was deactivated
            else:
                cursor.execute('UPDATE play_keys SET active=1 WHERE key_string=%s', (str(key),))
                db_connection.commit()

                botMessageChannelMessage = f'Playkey for user `{member_name}` has been reactivated. No account found.'

                note_message = f'Playkey reactivated by mythran. Date: {datetime.now()}'
            
            # Save a note for the user that their account/key was unlocked/reactivated
            self._save_record_entry(str(uuid), self.record_type.NOTE, note_message)

        # If the user does not have a play key
        else:
            botMessageChannelMessage = f'The user `{member_name}` does not have a playkey'

        cursor.close()
        db_connection.close()

        return botMessageChannelMessage


    def _generate_new_key(self):
        """
        Generates a new random key consisting of uppercase letters and digits, formatted in groups of four characters separated by dashes.
        
        Parameters:
            None
        
        Returns:
            key (str): A randomly generated key in the format XXXX-XXXX-XXXX-XXXX, where X is an uppercase letter or digit.
        """
        key = ""
        for j in range(4):
            key += ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(4)) + '-'

        # Remove last dash
        key = key[:-1]

        return key


    def _save_record_entry(self, uuid_str, record_type, note):
        '''
        Saves a record entry for a given UUID by updating the database with the provided note.

        Parameters:
            uuid_str (str): The unique identifier for the record to update.
            record_type (enum): The type of record to update (e.g., NOTE, OFFENSE, WARNING).
            note (str): The note or information to be added to the record.

        Returns:
            success (bool): True if the record was successfully updated, False otherwise.
        '''
        notes = self._pull_records(uuid_str)

        db_connection = self._get_db_connection()

        if not db_connection:
            print(f"{self._MODULE_NAME}: ERROR: Failed to save record entry for UUID {uuid_str}. No DB connection available.")
            return False

        if notes:
            if record_type == self.record_type.NOTE:
                notes["notes"].append(note)
            elif record_type == self.record_type.OFFENSE:
                notes["offenses"].append(note)
            elif record_type == self.record_type.WARNING:
                notes["warnings"].append(note)
            
            cursor = db_connection.cursor()
            cursor.execute('UPDATE play_keys SET notes=%s WHERE discord_uuid=%s', (json.dumps(notes), uuid_str))
            db_connection.commit()

            cursor.close()
            db_connection.close()

            return True
        else:
            db_connection.close()

            return False
        
        
    def _pull_records(self, uuid_str):
        """
        Retrieves and parses the notes associated with a given Discord UUID from the database.

        Parameters:
            uuid_str (str): The Discord UUID string used to query the database.

        Returns:
            result (dict or None): A dictionary containing the notes, offenses, and warnings if records are found.
                                   Returns a base structure with empty lists if no records exist.
                                   Returns None if the database connection fails or no result is found.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            return None

        try:
            # Get the notes for the user
            cursor = db_connection.cursor()
            cursor.execute('SELECT notes FROM play_keys WHERE discord_uuid=%s', (uuid_str,))
            result = cursor.fetchone()
            cursor.close()

            # If there is no result
            if not result:
                return None
            
            base_structure = {
                "notes": [],
                "offenses": [],
                "warnings": []
            }

            # If there are no records, return the base structure
            return json.loads(result[0]) if result[0] else base_structure
        finally:
            db_connection.close()


    def _format_user_records(self, records):
        """
        Formats user records into a structured and readable list of strings for display.

        Parameters:
            records (str or dict): The user records in JSON string format or as a dictionary. 
                                   Expected to contain "notes", "offenses", and "warnings" keys.

        Returns:
            formatted_records (list): A list of three formatted strings representing notes, offenses, 
                                       and warnings respectively. Each string is formatted for display.
        """
        # Convert JSON
        try:
            records = json.loads(records) if isinstance(records, str) else records
        except json.JSONDecodeError:
            print(f"{self._MODULE_NAME}: ERROR: Failed to decode JSON for records: {records}")
            records = {"notes": [], "offenses": [], "warnings": []}

        # Default structure if records are empty
        records = records if records else {"notes": [], "offenses": [], "warnings": []}

        # Format notes
        notes_display = "**__Notes:__**\n" + "\n".join(
            [
                f'[{i}]\n'
                f'  __Note__: {note["note"]}\n'
                f'  __Timestamp__: <t:{note["timestamp"]}:d> <t:{note["timestamp"]}:T>'
                for i, note in enumerate(records.get("notes", []))
            ]
        ) if records.get("notes") else "**__Notes:__**\nNo notes found."

        # Format offenses
        offenses_display = "**__Offenses:__**\n" + "\n".join(
            [
                f'[{i}]\n'
                f'  __Type__: {offense["type"]}\n'
                f'  __Offense__: {offense["offense"]}\n'
                f'  __Action Taken__: {offense["action-taken"]}\n'
                f'  __Timestamp__: <t:{offense["timestamp"]}:d> <t:{offense["timestamp"]}:T>'
                for i, offense in enumerate(records.get("offenses", []))
            ]
        ) if records.get("offenses") else "**__Offenses:__**\nNo offenses found."

        # Format warnings
        warnings_display = "**__Warnings:__**\n" + "\n".join(
            [
                f'[{i}]\n'
                f'  __Reason__: {warning["reason"]}\n'
                f'  __Timestamp__: <t:{warning["timestamp"]}:d> <t:{warning["timestamp"]}:T>'
                for i, warning in enumerate(records.get("warnings", []))
            ]
        ) if records.get("warnings") else "**__Warnings:__**\nNo warnings found."

        # Return the formatted sections as a list
        return [notes_display, offenses_display, warnings_display]


    def _dismiss_all_offenses(self, uuid_str):
        """
        Marks all offenses for a user as notified in the database.

        Parameters:
            uuid_str (str): The UUID of the user whose offenses need to be dismissed.

        Returns:
            success (bool): True if offenses were successfully dismissed, False otherwise.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            return False
        
        # Get record for the user
        record = self._pull_records(uuid_str)

        if not record:
            db_connection.close()
            return False
        
        # Check if there are any offenses
        if record.get("offenses"):
            # Mark all offenses as notified 
            for offense in record["offenses"]:
                offense["mod-notified"] = True

            # Update the record in the database
            cursor = db_connection.cursor()
            cursor.execute('UPDATE play_keys SET notes=%s WHERE discord_uuid=%s', (json.dumps(record), uuid_str))
            db_connection.commit()
            cursor.close()
            db_connection.close()

            return True
        else:
            print(f"{self._MODULE_NAME}: WARNING: No offenses found in record for user {uuid_str}\n")
            db_connection.close()
            return False
        
    def _dismiss_offense(self, uuid_str, offense):
        """
        Marks a specific offense as notified for a user in the database.

        Parameters:
            uuid_str (str): The unique identifier of the user (Discord UUID).
            offense (str): The offense to be marked as notified.

        Returns:
            success (bool): True if the offense was successfully marked as notified, 
                            False if the offense was not found or an error occurred.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            return False
        
        # Get record for the user
        record = self._pull_records(uuid_str)

        if not record:
            db_connection.close()
            return False
        
        # Check if the offense exists
        if offense in record.get("offenses", []):
            
            # Find the offense and mark as notified 
            offenses = record.get("offenses", [])
            for i, item in enumerate(offenses):
                if item == offense:
                    record["offenses"][i]["mod-notified"] = True
                    break

            # Update the record in the database
            cursor = db_connection.cursor()
            cursor.execute('UPDATE play_keys SET notes=%s WHERE discord_uuid=%s', (json.dumps(record), uuid_str))
            db_connection.commit()
            cursor.close()
            db_connection.close()

            return True
        else:
            print(f"{self._MODULE_NAME}: WARNING: Offense not found in record for user {uuid_str}\nOffense: {offense}\n")
            db_connection.close()
            return False


    def _is_playkey(self, string):
        """
        Checks if the given string matches the format of a play key.

        Parameters:
            string (str): The string to be checked against the play key format.

        Returns:
            bool: True if the string matches the play key format, False otherwise.
        """
        # This method checks if the given string matches the format of a play key.
        # A valid play key consists of four groups of four alphanumeric characters (A-Z, 0-9),
        # separated by hyphens (e.g., "ABCD-1234-EFGH-5678").
        pattern = re.compile(r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$')
        return bool(pattern.match(string))
    

    def _send_to_gpt(self, openAIClient, user_message):
        '''
        Sends a user message to the GPT model via the OpenAI client and retrieves the response.

        Parameters:
            openAIClient (object): The OpenAI client instance used to communicate with the GPT model.
            user_message (str): The message or query to be sent to the GPT model.

        Returns:
            response_content (str or None): The content of the GPT model's response if successful, 
                                            or None if an error occurs during the request.
        '''
        # Make the request to OpenAI
        try:
            response = openAIClient.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": WHITELIST_GPT_SYSTEM_MESSAGE},
                    {"role": "user", "content": user_message}
                ],
                temperature=.5,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0
            )
        except Exception as e:
            print(self._MODULE_NAME + ": ERROR: Failed to make request to OpenAI \n Error: " + str(e))
            return None
        
        if response.choices[0].message.content and DEBUG:
            print(self._MODULE_NAME + ": Raw GPT resonse: " + response.choices[0].message.content + "\n\n")  

        return response.choices[0].message.content


    def _get_key_from_user_id(self, user_id):
        '''
        Retrieves the key string associated with a given user ID from the database.

        Parameters:
            user_id (str): The Discord user ID for which the key string is to be retrieved.

        Returns:
            key_string (str or None): The key string associated with the user ID if found, 
                                      otherwise None.
        '''
        db_connection = self._get_db_connection()

        if not db_connection:
            return None

        cursor = db_connection.cursor()
        cursor.execute('SELECT key_string FROM play_keys WHERE discord_uuid=%s', (str(user_id),))
        result = cursor.fetchone()
        cursor.close()

        db_connection.close()
        return result[0] if result else None


    def _get_user_id_from_key(self, key):
        """
        Retrieves the Discord user ID associated with a given key from the database.

        Parameters:
            key (str): The key string used to look up the Discord user ID.

        Returns:
            result (str or None): The Discord user ID if the key exists in the database, 
                                  otherwise None.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            return None

        cursor = db_connection.cursor()
        cursor.execute('SELECT discord_uuid FROM play_keys WHERE key_string=%s', (key,))
        result = cursor.fetchone()
        cursor.close()

        db_connection.close()
        return result[0] if result else None


    def _make_game_announcement(self, title, message):
        """
        Sends a game announcement to a specified API endpoint.

        Parameters:
            title (str): The title of the announcement.
            message (str): The message content of the announcement.

        Returns:
            response_message (str): A message indicating the success or failure of the announcement delivery.
        """
        url = "http://localhost:2005/api/v1/announce"

        payload = {
            'title': title,
            'message': message
        }
        headers = {
            'accept': '*/*',
            'Content-Type': 'application/json'
        }

        response_message = ""

        # Make the request to send the announcement
        try:
            response = requests.post(url, json=payload, headers=headers)
        except requests.exceptions.ConnectionError:
            response_message = f'⚠️Failed to send announcement to the game\n`Connection Error`'
            return response_message
        except requests.exceptions.RequestException as e:
            print(f"{self._MODULE_NAME}: ERROR: Failed to send announcement: {e}")
            response_message = f'⚠️Failed to send announcement to the game\n`{e}`'
            return response_message
        
        if response.status_code == 200:
            response_message = f'Successfully sent announcement to the game'
        else:
            response_message = f'⚠️Failed to send announcement to the game\n```Response Code:{response.status_code}\nResponse Body: {response.json()}```'

        return response_message

