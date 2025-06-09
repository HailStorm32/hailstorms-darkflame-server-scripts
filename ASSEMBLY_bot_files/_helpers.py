import json
import random
import re
import requests
import string
from datetime import datetime
from ASSEMBLY_bot_files.ASSEMBLY_botSettings import WHITELIST_GPT_SYSTEM_MESSAGE, DEBUG, RSVD_OBJ_ID_START, TOTAL_RSVD_OBJ_IDS

BASE_CHAR_XML = '''<obj v="1"><mf hc="84" hs="1" hd="0" t="15" l="3" hdc="0" cd="27" lh="24357904" rh="23910596" es="1" ess="2" ms="2"/><char acct="%ID%" cc="0" gm="0" ft="0" llog="1749445712" ls="0" lzx="-626.5847" lzy="613.3515" lzz="-28.6374" lzrx="0.0" lzry="0.7015" lzrz="0.0" lzrw="0.7126" stt="0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;0;"><vl><l id="1000" cid="0"/></vl></char><dest hm="4" hc="4" im="0" ic="0" am="0" ac="0" d="0"/><inv><bag><b t="0" m="20"/><b t="1" m="40"/><b t="2" m="240"/><b t="3" m="240"/><b t="14" m="40"/></bag><items><in t="0"><i l="4517" id="1152921510479211844" s="0" c="1" eq="1" b="1"/><i l="2515" id="1152921510412760301" s="1" c="1" eq="1" b="1"/></in></items></inv><lvl l="1" cv="1" sb="500"/><flag></flag></obj>'''


class RecordTypes:
    """
    Enum for note types
    """
    def __init__(self):       
        self.NOTE = 0
        self.OFFENSE = 1
        self.WARNING = 2

        self.ALL = 999

class MigrationStates:
    """
    Enum for migration states
    """
    def __init__(self):       
        self.NOT_STARTED = 0
        self.WAITING_FOR_ACCOUNT = 1
        self.VALIDATE_ATTEMPT_1 = 2
        self.VALIDATE_ATTEMPT_2 = 3
        self.VALIDATE_ATTEMPT_3 = 4

        self.TOO_MANY_ATTEMPTS = 5
        self.ACCOUNT_VALIDATED = 6
        self.WAITING_FOR_SELECTION = 7
        self.TRANSFER_IN_PROGRESS = 8

        self.NO_MORE_OBJ_IDS = 9
        self.NO_BLU_ACCOUNT = 10
        self.NO_NEXUS_ACCOUNT = 11  # UNUSED
        self.COMPLETED = 12

        self.STATE_COUNT = self.COMPLETED + 1
class BotHelpers():
    """
    A mixin containing helper/utility functions, including DB logic.
    Expects that the final subclass sets 'self.mysql_connector'.
    """
    def __init__(self):
        self.record_type = RecordTypes()
        self.migration_state = MigrationStates()
        self.MAX_CHARACTER_SLOTS = 4

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
        
    def _get_blu_db_connection(self):
        """
        Get a database connection from the connection pool to the BLU database.

        Parameters:
            None

        Returns:
            connection (MySQLConnection or None): A MySQL connection object if successful, 
                              or None if the connection fails.
        """
        try:
            connection = self._blu_connection_pool.get_connection()
            if connection.is_connected():
                return connection
        except Exception as e:
            print(f"{self._MODULE_NAME}: ERROR: Failed to get BLU DB connection from pool: {e}")
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

    def _get_user_transfer_state(self, discord_uuid):
        """
        Retrieves the migration state for a given user ID from the database.

        Parameters:
            discord_uuid (str): The Discord UUID of the user whose migration state is to be retrieved.

        Returns:
            migration_state (int or None): The migration state associated with the user ID if found, 
                                            otherwise STATE_COUNT.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            return self.migration_state.STATE_COUNT

        cursor = db_connection.cursor()

        # Get state for the user
        cursor.execute('SELECT migration_state FROM blu_transfers WHERE discord_uuid=%s', (str(discord_uuid),))
        result = cursor.fetchone()

        # If they dont have a row, create a new entry for the user with NOT_STARTED state
        if not result:
            print(f"{self._MODULE_NAME}: WARNING: No column found for user {discord_uuid} when getting migration state. Defaulting to NOT_STARTED and creating new entry.")

            try:
                # Get play account id from the play key id for the user
                cursor.execute('SELECT id FROM accounts WHERE play_key_id IN (SELECT id FROM play_keys WHERE discord_uuid=%s)', (str(discord_uuid),))
                play_key_id_row = cursor.fetchone()
                play_key_id_result = play_key_id_row[0] if play_key_id_row else None

                if not play_key_id_result:
                    raise Exception(f"No play key found for user {discord_uuid} when creating new entry in blu_transfers table.")
                
                # Create a new entry for the user with NOT_STARTED state
                cursor.execute('INSERT INTO blu_transfers (account_id, discord_uuid, migration_state) VALUES (%s, %s, %s)', (play_key_id_result, str(discord_uuid), self.migration_state.NOT_STARTED))
                db_connection.commit()
            except Exception as e:  
                print(f"{self._MODULE_NAME}: ERROR: Failed to create new entry for user {discord_uuid} in blu_transfers table: {e}")
                cursor.close()
                db_connection.close()
                return self.migration_state.STATE_COUNT

            cursor.close()
            db_connection.close()
            return self.migration_state.NOT_STARTED

        return result[0] if result[0] < self.migration_state.STATE_COUNT else self.migration_state.STATE_COUNT
    
    def _set_user_transfer_state(self, user_id, state):
        """
        Updates the migration state for a given user ID in the blu_transfers table.

        Parameters:
            user_id (str): The unique identifier of the user whose migration state is to be updated.
            state (int): The new migration state to set for the user.

        Returns:
            success (bool): True if the migration state was successfully updated, False otherwise.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            print(f"{self._MODULE_NAME}: ERROR: No mysql connection, unable to set migration state")
            return False

        cursor = db_connection.cursor()

        # Update migration state in the blu_transfers table
        cursor.execute('UPDATE blu_transfers SET migration_state=%s WHERE discord_uuid=%s', (state, str(user_id)))
        db_connection.commit()
        
        if cursor.rowcount == 0:
            print(f"{self._MODULE_NAME}: ERROR: No blu_transfers row found for user {user_id} when setting migration state")
            cursor.close()
            db_connection.close()
            return False

        cursor.close()
        db_connection.close()

        return True

    def _validate_blu_account(self, blu_playkey):
        """
        Validates a Blu play key by checking if it exists in the Blu database and retrieves the number of characters associated with it.

        Parameters:
            blu_playkey (str): The Blu play key to be validated.

        Returns:
            list: [number_of_characters, blu_account_id]
              number_of_characters: int - Number of characters if account exists,
                              -1 if play key does not exist,
                              -2 if play key exists but no account,
                              -3 if DB connection fails.
              blu_account_id: int - Blu account ID if found, otherwise -1.
        """
        db_connection = self._get_blu_db_connection()

        account_id = -1

        if not db_connection:
            return [-3, account_id]

        cursor = db_connection.cursor()
        cursor.execute('SELECT id FROM play_keys WHERE key_string=%s', (blu_playkey,))
        result = cursor.fetchone()

        # If the account exists
        if result:
            # Get the account id from the play key id
            playkey_id = result[0]
            cursor.execute('SELECT id FROM accounts WHERE play_key_id=%s', (playkey_id,))
            result = cursor.fetchall()

            if not result or len(result) == 0:
                ret = [-2, account_id]
            else:
                account_id = result[0][0]

                # Get the number of characters associated with the account
                cursor.execute('SELECT COUNT(*) FROM charinfo WHERE account_id=%s', (account_id,))
                result = cursor.fetchall()
                ret = [result[0][0], account_id]
        else:
            ret = [-1, account_id]
    
        cursor.close()
        db_connection.close()

        return ret
    
    def _set_user_blu_account_id(self, discord_uuid, blu_account_id):
        """
        Sets the Blu account ID for a given Discord UUID in the database.

        Parameters:
            discord_uuid (str): The Discord UUID of the user.
            blu_account_id (int): The Blu account ID to be set for the user.

        Returns:
            success (bool): True if the Blu account ID was successfully set, False otherwise.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            print(f"{self._MODULE_NAME}: ERROR: No mysql connection, unable to set Blu account ID")
            return False

        cursor = db_connection.cursor()

        # Update the Blu account ID in the blu_transfers table
        cursor.execute('UPDATE blu_transfers SET blu_account_id=%s WHERE discord_uuid=%s', (blu_account_id, str(discord_uuid)))
        db_connection.commit()
        
        if cursor.rowcount == 0:
            print(f"{self._MODULE_NAME}: ERROR: No blu_transfers row found for user {discord_uuid} when setting Blu account ID")
            cursor.close()
            db_connection.close()
            return False
        cursor.close()
        db_connection.close()
        return True
    
    def _get_NU_characters(self, discord_uuid):
        """
        Retrieves the NU characters associated with a given Discord UUID from the database.

        Parameters:
            discord_uuid (str): The Discord UUID for which to retrieve characters.

        Returns:
            characters (list): A list of character names associated with the provided Discord UUID.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            return None

        cursor = db_connection.cursor()
        cursor.execute('SELECT name FROM charinfo WHERE account_id IN (SELECT id FROM accounts WHERE play_key_id IN (SELECT id FROM play_keys WHERE discord_uuid=%s))', (discord_uuid,))
        result = cursor.fetchall()
        
        # If there are no characters, return an empty list
        if not result:
            return []
        
        # Extract character names from the result
        characters = [row[0] for row in result]
        
        cursor.close()
        db_connection.close()

        return characters
    
    ####################################################################################################
    # Functions for executing transfer
    ####################################################################################################

    ############################---EXCEPTIONS---######################################
    class ObjectIDRangeError(Exception):
        """
        Raised when an object ID is out of the reserved range.
        """
        def __init__(self, message, object_id=None):
            super().__init__(message)
            self.message = message
            self.object_id = object_id

    class DatabaseConnectionError(Exception):
        """
        Raised when a database connection cannot be established.
        """
        def __init__(self, message):
            super().__init__(message)
            self.message = message
    
    class DatabaseFetchError(Exception):
        """
        Raised when a database fetch operation fails.
        """
        def __init__(self, message):
            super().__init__(message)
            self.message = message

    class NoAvailableCharacterSlotsError(Exception):
        """
        Raised when a user already has the maximum number of characters.
        """
        def __init__(self, message):
            super().__init__(message)
            self.message = message

    ##############################################################################

    def _get_object_id(self):
        """
        Retrieves the next available object ID from the migration_object_ids table and increments it.

        Returns:
            object_id (int): The next available object ID if found and within the reserved range.

        Raises:
            DatabaseConnectionError: If a DB connection cannot be established.
            ObjectIDRangeError: If the object ID is out of the reserved range.
            DatabaseFetchError: If no available object ID is found in the table.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            raise self.DatabaseConnectionError("No DB connection available, unable to get object ID")

        cursor = db_connection.cursor()
        cursor.execute('SELECT next_avail_id FROM migration_object_ids;')
        result = cursor.fetchone()

        if result:
            object_id = result[0]

            # Ensure the object ID is within the reserved range
            if object_id < RSVD_OBJ_ID_START or object_id > TOTAL_RSVD_OBJ_IDS:
                cursor.close()
                db_connection.close()
                raise self.ObjectIDRangeError(f"Object ID {object_id} is out of reserved range.", object_id)

            # Increment the next available object ID for future use
            cursor.execute('UPDATE migration_object_ids SET next_avail_id=%s;', (object_id + 1,))
            db_connection.commit()

            cursor.close()
            db_connection.close()
            return object_id
        
        else:
            cursor.close()
            db_connection.close()
            raise self.DatabaseFetchError("No available object ID found in migration_object_ids table.")

    def _create_new_character(self, discord_uuid, nu_account_id):
        """
        Creates a new character in the NU database for the specified Discord UUID and NU account ID.

        Parameters:
            discord_uuid (str): The Discord UUID of the user.
            nu_account_id (int): The NU account ID to be used for creating the new character.

        Returns:
            object_id (int): The object ID of the newly created character.

        Raises:
            DatabaseConnectionError: If a DB connection cannot be established.
            NoAvailableCharacterSlotsError: If the user already has the maximum number of characters.
            ObjectIDRangeError: If the object ID is out of the reserved range.
            DatabaseFetchError: If no available object ID is found in the table.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            raise self.DatabaseConnectionError("No Blu DB connection available")

        cursor = db_connection.cursor()

        try:
            # Ensure there is space for the new character
            nu_characters = self._get_NU_characters(discord_uuid)

            if nu_characters is None:
                raise Exception(f"Failed to retrieve NU characters for Discord UUID {discord_uuid}")
            elif self.MAX_CHARACTER_SLOTS - len(nu_characters) <= 0:
                raise self.NoAvailableCharacterSlotsError(f"User {discord_uuid} already has the maximum number of characters ({self.MAX_CHARACTER_SLOTS}).")
            
            # Grab the next available object ID for the new character
            object_id = self._get_object_id()

            # Create new character entry in the charinfo table
            cursor.execute('INSERT INTO charinfo (id, account_id, name, pending_name, needs_rename) VALUES (%s, %s, %s, %s, %s);', (object_id, nu_account_id, f"{object_id}", "", 1))
            db_connection.commit()
            print(f"{self._MODULE_NAME}: Successfully created new charxml entry with ID {object_id} for account ID {nu_account_id}")

            # Create new character xml in the charxml table
            char_xml = str(BASE_CHAR_XML)
            char_xml = char_xml.replace("%ID%", str(nu_account_id))

            cursor.execute('INSERT INTO charxml (id, xml_data) VALUES (%s, %s);', (object_id, char_xml))
            db_connection.commit()
            print(f"{self._MODULE_NAME}: Successfully created new charxml entry with ID {object_id} for account ID {nu_account_id}")

            return object_id

        finally:
            if cursor:
                cursor.close()
            if db_connection:
                db_connection.close()


    def _main_migration_loop():
        """
        Main migration loop that processes users in the migration queue and performs necessary actions.

        This function continuously checks for users in the migration queue, retrieves their information,
        and performs the migration process for each user until the queue is empty.
        """
        # This function is a placeholder for the main migration loop logic.
        # It should be implemented to handle the migration process for users in the queue.
        pass
    