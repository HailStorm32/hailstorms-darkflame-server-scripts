import asyncio
import json
import random
import re
import discord
import requests
import string
import time
from datetime import datetime
import queue
import time
import xmltodict
import xml.etree.ElementTree as ET
from ASSEMBLY_bot_files.ASSEMBLY_botSettings import (
    WHITELIST_GPT_SYSTEM_MESSAGE,
    DEBUG,
    RSVD_OBJ_ID_START,
    TOTAL_RSVD_OBJ_IDS,
    BOT_CHANNEL,
    MIGRATIONS_ENABLED,
)

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

        self.SELECTION_BEGIN = 2
        self.WAITING_FOR_SELECTION = 3
        self.TRANSFER_QUEUED = 4
        self.TRANSFER_IN_PROGRESS = 5

        self.ERROR_STATE = 6
        self.COMPLETED = 7

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
        self.migration_queue = queue.Queue()
        self.used_item_ids = []
        self.migrations_enabled = MIGRATIONS_ENABLED
        self.active_migration_views = set()

        self._state_names = {
            0: "NOT_STARTED",
            1: "WAITING_FOR_ACCOUNT",
            2: "SELECTION_BEGIN",
            3: "WAITING_FOR_SELECTION",
            4: "TRANSFER_QUEUED",
            5: "TRANSFER_IN_PROGRESS",
            6: "ERROR_STATE",
            7: "COMPLETED",
        }

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
        timeout = 10  # seconds
        poll_interval = 0.5  # seconds
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                connection = self._connection_pool.get_connection()
                if connection.is_connected():
                    return connection
            except Exception as e:
                print(f"{self._MODULE_NAME}: WARNING: DB connection not available yet: {e}")
                time.sleep(poll_interval)
        print(f"{self._MODULE_NAME}: ERROR: Timed out waiting for DB connection from pool.")
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
        timeout = 10  # seconds
        poll_interval = 0.5  # seconds
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                connection = self._blu_connection_pool.get_connection()
                if connection.is_connected():
                    return connection
            except Exception as e:
                print(f"{self._MODULE_NAME}: WARNING: BLU DB connection not available yet: {e}")
                time.sleep(poll_interval)
        print(f"{self._MODULE_NAME}: ERROR: Timed out waiting for BLU DB connection from pool.")
        return None

    def _lock_account(self, member_name, uuid, player_left=True, log_note=True):
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
                    
                    # Create a note object
                    note_obj = {"timestamp": int(time.time()), "note": f'Account locked on leave. Date: {datetime.now()}'}
                else:
                    botMessageChannelMessage = f'Account has been locked for user `{member_name}`.'

                    # Create a note object
                    note_obj = {"timestamp": int(time.time()), "note": f'Account locked by mythran. Date: {datetime.now()}'}
            
            #If the key has not been used, deactivate it
            else:
                cursor.execute('UPDATE play_keys SET active=0 WHERE key_string=%s', (str(key),))
                db_connection.commit()
                cursor.close()

                if player_left:
                    botMessageChannelMessage = f'The user `{member_name}` has left the server. Play key found, but no account. \n **Key has been deactivated.**\nTheir play key was: `{key}`'

                    # Create a note object
                    note_obj = {"timestamp": int(time.time()), "note": f'Playkey deactivated on leave. Date: {datetime.now()}'}
                    
                else:
                    botMessageChannelMessage = f'Playkey for user `{member_name}` has been deactivated. No account found.'

                    # Create a note object
                    note_obj = {"timestamp": int(time.time()), "note": f'Playkey deactivated by mythran. Date: {datetime.now()}'}
            
            #Save a note for the user that their account/key was locked
            if log_note:
                self._save_record_entry(str(uuid), self.record_type.NOTE, note_obj)

        #If the user does not have a play key
        else:
            if player_left:
                botMessageChannelMessage = f'The user `{member_name}` has left the server. **No play key found for them.**'
            else:
                botMessageChannelMessage = f'The user `{member_name}` does not have a playkey'

        db_connection.close()

        return botMessageChannelMessage 


    def _unlock_account(self, member_name, uuid, log_note=True):
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

                # Create a note object
                note_obj = {"timestamp": int(time.time()), "note": f'Account unlocked by mythran. Date: {datetime.now()}'}

            # Reactivate the play key if it was deactivated
            else:
                cursor.execute('UPDATE play_keys SET active=1 WHERE key_string=%s', (str(key),))
                db_connection.commit()

                botMessageChannelMessage = f'Playkey for user `{member_name}` has been reactivated. No account found.'

                # Create a note object
                note_obj = {"timestamp": int(time.time()), "note": f'Playkey reactivated by mythran. Date: {datetime.now()}'}
            
            # Save a note for the user that their account/key was unlocked/reactivated
            if log_note:
                self._save_record_entry(str(uuid), self.record_type.NOTE, note_obj)

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

        try:
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
                    
                    return self.migration_state.STATE_COUNT

                return self.migration_state.NOT_STARTED

            return result[0] if result[0] < self.migration_state.STATE_COUNT else self.migration_state.STATE_COUNT

        finally:
            if cursor:
                cursor.close()
            if db_connection:
                db_connection.close()
    
    def _set_user_transfer_state(self, user_id, state, error_code=0):
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
        
        # If the state is ERROR_STATE, set the error code
        if state == self.migration_state.ERROR_STATE:
            cursor.execute('UPDATE blu_transfers SET error_state=%s WHERE discord_uuid=%s', (error_code, str(user_id)))
            db_connection.commit()
            if cursor.rowcount == 0:
                print(f"{self._MODULE_NAME}: ERROR: No blu_transfers row found for user {user_id} when setting error code")
                cursor.close()
                db_connection.close()
                return False

        cursor.close()
        db_connection.close()

        return True

    def _validate_blu_account(self, blu_playkey):
        """
        Validates a Blu play key by checking if it exists in the Blu database and returns information about its status.

        Parameters:
            blu_playkey (str): The Blu play key to validate.

        Returns:
            list: [status_code, blu_account_id]
            status_code (int):
                >0 : Number of characters if account exists and is unclaimed,
                -1 : Play key does not exist,
                -2 : Play key exists but no account found,
                -3 : Database connection failed,
                -4 : Account already claimed by a Discord user.
            blu_account_id (int): Blu account ID if found, otherwise -1.
        """
        blu_db_connection = self._get_blu_db_connection()
        nu_db_connection = self._get_db_connection()

        account_id = -1

        if not blu_db_connection or not nu_db_connection:
            return [-3, account_id]

        blu_cursor = blu_db_connection.cursor()
        blu_cursor.execute('SELECT id FROM play_keys WHERE key_string=%s', (blu_playkey,))
        result = blu_cursor.fetchone()

        # If the account exists
        if result:
            # Get the account id from the play key id
            playkey_id = result[0]
            blu_cursor.execute('SELECT id FROM accounts WHERE play_key_id=%s', (playkey_id,))
            result = blu_cursor.fetchall()

            if not result or len(result) == 0:
                ret = [-2, account_id]
            else:
                account_id = result[0][0]

                # Ensure the account already hasn't been "claimed" by a discord user
                nu_cursor = nu_db_connection.cursor()
                nu_cursor.execute('SELECT COUNT(*) FROM blu_transfers WHERE blu_account_id=%s', (account_id,))
                result = nu_cursor.fetchone()
                if result and result[0] > 0:
                    ret = [-4, account_id]
                else:
                    # Get the number of characters associated with the account
                    blu_cursor.execute('SELECT COUNT(*) FROM charinfo WHERE account_id=%s', (account_id,))
                    result = blu_cursor.fetchall()
                    ret = [result[0][0], account_id]
        else:
            ret = [-1, account_id]
    
        blu_cursor.close()
        blu_db_connection.close()
        nu_cursor.close()
        nu_db_connection.close()

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

    def _get_user_transfer_info(self, discord_uuid):
        """
        Fetch the transfer information for the given Discord UUID from the
        ``blu_transfers`` table.

        Parameters:
            discord_uuid (str): The Discord UUID of the user.

        Returns:
            dict or None: A dictionary containing the row data if found,
            otherwise ``None``. ``chosen_chars`` is returned as a parsed
            Python object if present.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            print(f"{self._MODULE_NAME}: ERROR: No mysql connection, unable to get transfer info")
            return None

        cursor = db_connection.cursor()
        cursor.execute('SELECT * FROM blu_transfers WHERE discord_uuid=%s', (str(discord_uuid),))
        result = cursor.fetchone()
        cursor.close()
        db_connection.close()

        if not result:
            return None

        transfer_info = {
            "id": result[0],
            "discord_uuid": result[1],
            "account_id": result[2],
            "blu_account_id": result[3],
            "migration_state": result[4],
            "attempts": result[5],
            "chosen_chars": json.loads(result[6]) if result[6] else None,
            "error_state": result[7],
        }

        return transfer_info

    def _get_inprogress_transfers(self):
        """
        Retrieves a list of all transfers that are underway (not NOT_STARTED or COMPLETED).

        Returns:
            list: A list of dictionaries containing 'discord_uuid' and 'migration_state' for each in-progress transfer.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            return []

        cursor = db_connection.cursor(dictionary=True)
        cursor.execute(
            (
                'SELECT discord_uuid, migration_state, error_state '
                'FROM blu_transfers '
                'WHERE migration_state > %s AND migration_state != %s'
            ),
            (self.migration_state.NOT_STARTED, self.migration_state.COMPLETED),
        )
        rows = cursor.fetchall()
        cursor.close()
        db_connection.close()
        return rows

    def _get_queued_migrations(self):
        """
        Returns a snapshot list of queued migration requests.

        Returns:
            list: A list of migration request dictionaries currently in the queue.
        """
        return list(self.migration_queue.queue)

    async def _disable_active_migration_views(self):
        """
        Disable all active migration selection views and reset their state.

        Returns:
            None
        """
        views = list(self.active_migration_views)
        for view in views:
            try:
                await view._disable_all_items()
                await asyncio.to_thread(
                    self._set_user_transfer_state,
                    view.user_id,
                    self.migration_state.SELECTION_BEGIN,
                )
            except Exception as e:
                print(
                    f"{self._MODULE_NAME}: ERROR disabling migration view for {view.user_id}: {e}"
                )
        self.active_migration_views.clear()

    def _migration_state_to_str(self, state):
        """
        Translates a migration state integer to its string label.

        Parameters:
            state (int): The migration state integer.

        Returns:
            str: The string label corresponding to the migration state.
        """
        return self._state_names.get(state, f"UNKNOWN({state})")

    def _set_user_migration_selection(self, discord_uuid, selection_dict):
        """
        Save the user's migration selections (characters to delete and
        characters to migrate) into the ``blu_transfers`` table.

        Parameters:
            discord_uuid (str): The Discord UUID of the user.
            selection_dict (dict): Dictionary describing the user's choices.
            Expected format:
                {"delete_nu": [delete_ids], "migrate_blu": [transfer_ids]}

        Returns:
            bool: ``True`` if the update succeeds, ``False`` otherwise.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            print(f"{self._MODULE_NAME}: ERROR: No mysql connection, unable to set migration selection")
            return False

        cursor = db_connection.cursor()

        try:
            payload = json.dumps(selection_dict)
            cursor.execute(
                'UPDATE blu_transfers SET chosen_chars=%s WHERE discord_uuid=%s',
                (payload, str(discord_uuid))
            )
            db_connection.commit()
            success = cursor.rowcount > 0
        except Exception as e:
            print(f"{self._MODULE_NAME}: ERROR updating migration selection for user {discord_uuid}: {e}")
            success = False

        cursor.close()
        db_connection.close()

        return success
    
    def _get_NU_characters(self, discord_uuid):
        """
        Retrieves the NU characters associated with a given Discord UUID from the database.

        Parameters:
            discord_uuid (str): The Discord UUID for which to retrieve characters.

        Returns:
            characters (list): A list of tuples (character_name, character_id) associated with the provided Discord UUID.
        """
        db_connection = self._get_db_connection()

        if not db_connection:
            return None

        try:
            cursor = db_connection.cursor()
            cursor.execute('SELECT name,id FROM charinfo WHERE account_id IN (SELECT id FROM accounts WHERE play_key_id IN (SELECT id FROM play_keys WHERE discord_uuid=%s))', (discord_uuid,))
            result = cursor.fetchall()
            
            # If there are no characters, return an empty list
            if not result:
                return []
            
            # Extract character names and IDs from the result
            characters = [(row[0], row[1]) for row in result]

            return characters
        
        finally:
            if cursor:
                cursor.close()
            if db_connection:
                db_connection.close()

    def _get_BLU_characters(self, blu_account_id):
        """
        Retrieves the BLU characters associated with a given Blu account ID from the database.

        Parameters:
            blu_account_id (int): The Blu account ID for which to retrieve characters.

        Returns:
            characters (list): A list of tuples (character_name, character_id) associated with the provided Blu account ID.
        """
        db_connection = self._get_blu_db_connection()

        if not db_connection:
            return None
        
        try:
            cursor = db_connection.cursor()
            cursor.execute('SELECT name,id FROM charinfo WHERE account_id=%s', (blu_account_id,))
            result = cursor.fetchall()
            
            # If there are no characters, return an empty list
            if not result:
                return []
            
            # Extract character names and IDs from the result
            characters = [(row[0], row[1]) for row in result]

            return characters

        finally:
            if cursor:
                cursor.close()
            if db_connection:
                db_connection.close()

    def _get_BLU_character_name(self, char_id):
        """Return the name of a BLU character given its ID."""
        db = self._get_blu_db_connection()
        if not db:
            return str(char_id)
        try:
            cur = db.cursor()
            cur.execute('SELECT name FROM charinfo WHERE id=%s', (char_id,))
            row = cur.fetchone()
            return row[0] if row else str(char_id)
        finally:
            cur.close()
            db.close()

    def _get_NU_character_name(self, char_id):
        """Return the name of a NU character given its ID."""
        db = self._get_db_connection()
        if not db:
            return str(char_id)
        try:
            cur = db.cursor()
            cur.execute('SELECT name FROM charinfo WHERE id=%s', (char_id,))
            row = cur.fetchone()
            return row[0] if row else str(char_id)
        finally:
            cur.close()
            db.close()
    
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

    class CorruptCharacterXML(Exception):
        """
        Raised when a character XML is found to be corrupt.
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

        try:
            cursor = db_connection.cursor()
            cursor.execute('SELECT next_avail_id FROM migration_object_ids;')
            result = cursor.fetchone()

            if result:
                object_id = result[0]

                # Ensure the object ID is within the reserved range
                if object_id < RSVD_OBJ_ID_START:
                    raise self.ObjectIDRangeError(f"Object ID {object_id} is out of reserved range.", object_id)

                # Ensure server object IDs haven't encroached on our reserved range
                cursor.execute('SELECT * FROM object_id_tracker;')
                result2 = cursor.fetchone()
                if result2[0] >= RSVD_OBJ_ID_START:
                    raise self.ObjectIDRangeError(f"Server object IDs have encroached on our reserved range.", result2[0])

                # Increment the next available object ID for future use
                cursor.execute('UPDATE migration_object_ids SET next_avail_id=%s;', (object_id + 1,))
                db_connection.commit()

                return object_id
            
            else:
                raise self.DatabaseFetchError("No available object ID found in migration_object_ids table.")
            
        finally:
            if cursor:
                cursor.close()
            if db_connection:
                db_connection.close()

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
            print(f"{self._MODULE_NAME} {MIGRATION_TAG}: Successfully created new charinfo entry with ID {object_id} for discord ID {discord_uuid}")

            # Create new character xml in the charxml table
            char_xml = str(BASE_CHAR_XML)
            char_xml = char_xml.replace("%ID%", str(nu_account_id))

            cursor.execute('INSERT INTO charxml (id, xml_data) VALUES (%s, %s);', (object_id, char_xml))
            db_connection.commit()
            print(f"{self._MODULE_NAME} {MIGRATION_TAG}: Successfully created new charxml entry with ID {object_id} for discord ID {discord_uuid}")

            return object_id

        finally:
            if cursor:
                cursor.close()
            if db_connection:
                db_connection.close()

    def _get_all_item_ids(self, db_connection):
        """
        Retrieves all item IDs from every character in the database

        Parameters:
            db_connection (object): The database connection object.

        Returns:
            item_ids (list): A list of all item IDs
        """
        try:
            item_ids = []

            # Get all the character XMLs from the charxml table
            cursor = db_connection.cursor()
            cursor.execute("SELECT id,xml_data FROM charxml")
            char_xmls = cursor.fetchall()

            for char_id, xml in char_xmls:
                if not xml or not xml.strip():
                    print(f"{self._MODULE_NAME} {MIGRATION_TAG}: Empty XML for Character ID {char_id}, skipping.")
                    continue

                try:
                    root = ET.fromstring(xml)
                except ET.ParseError as e:
                    print(f"{self._MODULE_NAME} {MIGRATION_TAG}: Failed to parse XML for Character ID {char_id}: {e}")
                    continue

                item_ids.extend([
                    elem.attrib['id']
                    for elem in root.findall('.//items//i')
                    if 'id' in elem.attrib
                ]) 

            return item_ids

        finally:
            if cursor:
                cursor.close()

    def _generate_item_id(self):
        """
        Generates a unique 64-bit item ID with the 32nd and 60th bits set.

        This function generates a random 64-bit integer, ensuring that the 32nd and 60th bits are always set.
        It checks that the generated ID is not already present in the used_item_ids list and not present in the relevant database tables.

        Returns:
            new_id (int): A unique 64-bit integer item ID with the 32nd and 60th bits set.

        Raises:
            DatabaseConnectionError: If a Blu DB connection cannot be established.
        """
        # Bits to set for new IDs
        BIT_32 = 1 << 32
        BIT_60 = 1 << 60

        db_connection = self._get_blu_db_connection()
        if not db_connection:
            raise self.DatabaseConnectionError("No Blu DB connection available, unable to check item ID in properties_contents table")
        cursor = db_connection.cursor()

        while True:
            rand32 = random.getrandbits(32)
            new_id = rand32 | BIT_32 | BIT_60

            # Check if the new ID is already in use
            if new_id in self.used_item_ids:
                continue         

            # Check if new ID is used in the properties_contents table
            cursor.execute('SELECT COUNT(*) FROM properties_contents WHERE id=%s', (new_id,))
            result = cursor.fetchone()
            if result and result[0] > 0:
                continue

            # Check if the new ID is already in use in the ugc_modular_build table
            cursor.execute('SELECT COUNT(*) FROM ugc_modular_build WHERE ugc_id=%s', (new_id,))
            result = cursor.fetchone()
            if result and result[0] > 0:
                continue

            # If we reach here, the new ID is unique and can be used
            self.used_item_ids.append(new_id)
            cursor.close()
            db_connection.close()
            return new_id
    
    def _delete_character(self, character_id):
        """
        Deletes a character and all related data from the database.

        Parameters:
            character_id (int): The ID of the character to delete.

        Raises:
            DatabaseConnectionError: If a DB connection cannot be established.
        """
        db_connection = self._get_db_connection()
        if not db_connection:
            raise self.DatabaseConnectionError("No Blu DB connection available, unable to delete character")

        cursor = db_connection.cursor()

        try:
            queries = [
                ("DELETE FROM charxml WHERE id=%s LIMIT 1;", (character_id,)),
                ("DELETE FROM command_log WHERE character_id=%s;", (character_id,)),
                ("DELETE FROM friends WHERE player_id=%s OR friend_id=%s;", (character_id, character_id)),
                ("DELETE FROM leaderboard WHERE character_id=%s;", (character_id,)),
                ("DELETE FROM properties_contents WHERE property_id IN (SELECT id FROM properties WHERE owner_id=%s);", (character_id,)),
                ("DELETE FROM properties WHERE owner_id=%s;", (character_id,)),
                ("DELETE FROM ugc WHERE character_id=%s;", (character_id,)),
                ("DELETE FROM activity_log WHERE character_id=%s;", (character_id,)),
                ("DELETE FROM mail WHERE receiver_id=%s;", (character_id,)),
                ("DELETE FROM charinfo WHERE id=%s LIMIT 1;", (character_id,))
            ]

            for statement, params in queries:
                cursor.execute(statement, params)
            db_connection.commit()

        finally:
            cursor.close()
            db_connection.close()

    def _pull_and_clean_char_xml(self, blu_character_id, nu_account_id, ugc_id_pairs):
        """
        Retrieves and cleans the character XML for a given BLU character ID.

        Parameters:
            blu_character_id (int): The BLU character ID whose XML is to be retrieved and cleaned.
            nu_account_id (int): The NU account ID to update in the XML.
            ugc_id_pairs (list): A list of tuples (old_ugc_id, new_ugc_id) for modular UGC migration.

        Returns:
            cleaned_xml (str): The cleaned character XML string.

        Raises:
            DatabaseConnectionError: If a Blu DB connection cannot be established.
            DatabaseFetchError: If no character XML is found for the given BLU character ID.
            CorruptCharacterXML: If the character XML is corrupt or cannot be parsed.
        """
        INV_ITEMS = "0"
        INV_VAULT_ITEMS = "1"
        INV_BRICKS = "2"
        INV_MODELS_IN_BBB = "3"
        INV_TEMP_ITEMS = "4"
        INV_MODELS = "5"
        INV_TEMP_MODELS = "6"
        INV_BEHAVIORS = "7"
        INV_PROPERTY_DEEDS = "8"
        INV_BRICKS_IN_BBB = "9"
        INV_VENDOR = "10"
        INV_VENDOR_BUYBACK = "11"
        INV_QUEST = "12"
        INV_DONATION = "13"
        INV_VAULT_MODELS = "14"
        INV_ITEM_SETS = "15"


        db_connection = self._get_blu_db_connection()

        if not db_connection:
            raise self.DatabaseConnectionError("No Blu DB connection available")

        cursor = db_connection.cursor()

        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: INFO: Pulling character XML for BLU character ID {blu_character_id} and updating...")
        
        try:
            # Retrieve the character XML from the charxml table
            cursor.execute('SELECT xml_data FROM charxml WHERE id=%s', (blu_character_id,))
            result = cursor.fetchone()

            if not result:
                raise self.DatabaseFetchError(f"No character XML found for BLU character ID {blu_character_id}")

            char_xml = result[0]

            # Convert xml to a dictionary
            try:
                xml_dict = xmltodict.parse(char_xml)
            except:
                raise self.CorruptCharacterXML(f"Corrupt character XML for BLU character ID {blu_character_id}")
            
            #############################################
            # Update the object ID in the XML
            #############################################
            xml_dict['obj']['char']['@acct'] = str(nu_account_id)


            #############################################
            # Remove pets
            # NOTE: Migration code assumes pets are removed from the character XML.
            #     Not removing them will cause issues with subkey updating
            #############################################
            if "pet" in xml_dict["obj"] and xml_dict["obj"]["pet"] != None and len(xml_dict["obj"]["pet"]["p"]) > 1:
                
                # Collect all pet IDs
                pets = xml_dict["obj"]["pet"]["p"]
                if not isinstance(pets, list):
                    pets = [pets]
                pet_ids = [ p["@id"] for p in pets ]

                # Find the INV_MODELS (<in t="5">) block
                inventories = xml_dict["obj"]["inv"]["items"]["in"]
                for inv in inventories:
                    # Check if the inventory is of type INV_MODELS
                    if inv["@t"] == INV_MODELS:
                        
                        if isinstance(inv["i"], list):
                            # Rebuild the inventory list without the pets
                            inv["i"] = [item for item in inv["i"] if item["@sk"] not in pet_ids]
                        else:
                            print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: Expected a list of items in INV_MODELS, but found a single item. Skipping pet removal for this item.")

                xml_dict["obj"]["pet"] = {"p": []}  # Keep the pet tag but make it empty

                print(f"{self._MODULE_NAME} {MIGRATION_TAG}: INFO: Removed pets from character XML")


            #############################################
            # Update item IDs in the XML
            #############################################
            print(f"{self._MODULE_NAME} {MIGRATION_TAG}: INFO: Updating item IDs in character XML if collisions are found...")

            # Cycle through all inventory types and update item IDs if there are collisions
            for inventory_type in xml_dict["obj"]["inv"]["items"]["in"]:
                # Skip empty inventory types
                if len(inventory_type) <= 1:
                    continue

                if inventory_type["@t"] == INV_ITEMS or inventory_type["@t"] == INV_VAULT_ITEMS or inventory_type["@t"] == INV_BRICKS or inventory_type["@t"] == INV_QUEST:
                    if not isinstance(inventory_type["i"], list):
                        # If the inventory type has a single item, convert it to a list
                        inventory = [inventory_type["i"]]
                    else:
                        inventory = inventory_type["i"]

                    # Go through each item in the inventory type and check if the item ID already exists and update it if necessary
                    for item in inventory:
                        if item["@id"] in self.used_item_ids:
                            new_id = str(self._generate_item_id())

                            # Ensure the ID we are replacing isn't a parent of an item in INV_ITEM_SETS
                            # If it is, replace it with a new ID
                            item_sets_inventory = next( (inv for inv in xml_dict["obj"]["inv"]["items"]["in"] if inv["@t"] == INV_ITEM_SETS), None)
                            if item_sets_inventory and len(item_sets_inventory) > 1:
                                if not isinstance(item_sets_inventory["i"], list):
                                    item_sets_inv_items = [item_sets_inventory["i"]]
                                else:
                                    item_sets_inv_items = item_sets_inventory["i"]
                                    
                                for item_sets_inv_item in item_sets_inv_items:
                                    if item_sets_inv_item["@parent"] == item["@id"]:
                                        item_sets_inv_item["@parent"] = new_id
                                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: INFO: Replaced parent ID to [{new_id}] of item lot [{item_sets_inv_item['@l']}] in inventory type {INV_ITEM_SETS}.")
                            
                            old_id = item["@id"]
                            item["@id"] = new_id
                            print(f"{self._MODULE_NAME} {MIGRATION_TAG}: INFO: Updated item ID from [{old_id}] to [{new_id}] in inventory type {inventory_type['@t']} for item lot [{item['@l']}].")

                elif inventory_type["@t"] == INV_MODELS_IN_BBB:
                    pass # Skip
                elif inventory_type["@t"] == INV_TEMP_ITEMS:
                    pass # Skip
                elif inventory_type["@t"] == INV_MODELS or inventory_type["@t"] == INV_VAULT_MODELS:
                    if not isinstance(inventory_type["i"], list):
                        # If the inventory type has a single item, convert it to a list
                        inventory = [inventory_type["i"]]
                    else:
                        inventory = inventory_type["i"]

                    for item in inventory:
                        if item["@id"] in self.used_item_ids:
                            new_id = str(self._generate_item_id())
                            
                            old_id = item["@id"]
                            item["@id"] = new_id
                            print(f"{self._MODULE_NAME} {MIGRATION_TAG}: INFO: Updated item ID from [{old_id}] to [{new_id}] in inventory type {inventory_type['@t']} for item lot [{item['@l']}].")

                        # If the subkey was was updated in the database, update it in the XML
                        new_subkey_id = next((str(pair[1]) for pair in ugc_id_pairs if str(pair[0]) == item["@sk"]), None)
                        if new_subkey_id:
                            item["@sk"] = new_subkey_id
                            print(f"{self._MODULE_NAME} {MIGRATION_TAG}: INFO: Updated item subkey to {new_subkey_id} in inventory type {inventory_type['@t']} for item lot [{item['@l']}].")

                    pass
                elif inventory_type["@t"] == INV_TEMP_MODELS:
                    pass # Skip
                elif inventory_type["@t"] == INV_BEHAVIORS:
                    pass # Skip ??
                elif inventory_type["@t"] == INV_PROPERTY_DEEDS:
                    pass # Skip
                elif inventory_type["@t"] == INV_BRICKS_IN_BBB:
                    pass # Skip
                elif inventory_type["@t"] == INV_VENDOR:
                    pass # Skip
                elif inventory_type["@t"] == INV_VENDOR_BUYBACK:
                    pass # Skip
                elif inventory_type["@t"] == INV_DONATION:
                    pass # Skip
                elif inventory_type["@t"] == INV_ITEM_SETS:
                    pass # TODO

            #############################################
            # Convert the dictionary back to XML
            #############################################
            cleaned_xml = xmltodict.unparse(xml_dict)

            # #debug write to file
            # with open(f"debug_charxml_{blu_character_id}.xml", "w") as f:
            #     xmltodict.unparse(xml_dict, pretty=True, output=f)

            return cleaned_xml

        finally:
            if cursor:
                cursor.close()
            if db_connection:
                db_connection.close()

    def _migrate_properties(self, nu_account_id, blu_character_id, new_character_id):
        """
        Migrates properties and related UGC from the BLU character to a NU character.

        Parameters:
            nu_account_id (int): The NU account ID to which properties and UGC will be migrated.
            blu_character_id (int): The BLU character ID whose properties and UGC will be migrated.
            new_character_id (int): The new character ID in the NU database where properties and UGC will be applied.

        Returns:
            None

        Raises:
            DatabaseConnectionError: If a database connection cannot be established.
            DatabaseFetchError: If required data cannot be fetched from the database.
            ObjectIDRangeError: If a new UGC or property ID cannot be generated.
        """
        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: INFO: Migrating properties and related UGC from BLU character {blu_character_id} to NU character {new_character_id} ...")

        nu_db_connection = self._get_db_connection()
        blu_db_connection = self._get_blu_db_connection()
        
        if not nu_db_connection or not blu_db_connection:
            raise self.DatabaseConnectionError("No database connection available for migrating properties.")

        nu_db_cursor = nu_db_connection.cursor()
        blu_db_cursor = blu_db_connection.cursor()

        try:
            # Get the clone id for the new character in the NU database
            nu_db_cursor.execute('SELECT prop_clone_id FROM charinfo WHERE id=%s', (new_character_id,))
            clone_id_result = nu_db_cursor.fetchone()
            if not clone_id_result:
                raise self.DatabaseFetchError(f"No clone ID found for new character ID {new_character_id} in NU database.")
            new_clone_id = clone_id_result[0]

            # Get all the properties from the BLU database for the old character
            blu_db_cursor.execute('SELECT * FROM properties WHERE owner_id=%s', (blu_character_id,))
            properties = blu_db_cursor.fetchall()
            if not properties:
                print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: No properties found for BLU character {blu_character_id}. Skipping property migration.")
                return
            print(f"{self._MODULE_NAME} {MIGRATION_TAG}: INFO: Found {len(properties)} properties for BLU character {blu_character_id}. Migrating...")

            # Iterate through each property and migrate it to the NU database
            for prop in properties:
                prop_dict = {
                    "id": prop[0],
                    "owner_id": prop[1],
                    "template_id": prop[2],
                    "clone_id": prop[3],
                    "name": prop[4],
                    "description": prop[5],
                    "rent_amount": prop[6],
                    "rent_due": prop[7],
                    "privacy_option": prop[8],
                    "mod_approved": prop[9],
                    "last_updated": prop[10],
                    "time_claimed": prop[11],
                    "rejection_reason": prop[12],
                    "reputation": prop[13],
                    "zone_id": prop[14],
                    "performance_cost": prop[15],
                }

                # Generate a new property ID
                while True:
                    new_id = random.getrandbits(32)
                    nu_db_cursor.execute('SELECT id FROM properties WHERE id=%s', (new_id,)) # Check if the new ID already exists
                    if not nu_db_cursor.fetchone():
                        break

                # Update the property id
                old_prop_id = prop_dict["id"]  # Store the old property ID for migrating the contents
                prop_dict["id"] = new_id

                # Update the clone_id
                prop_dict["clone_id"] = new_clone_id

                # Update the owner id
                prop_dict["owner_id"] = new_character_id

                # Insert the property into the NU database 
                nu_db_cursor.execute(
                    'INSERT INTO properties (id, owner_id, template_id, clone_id, name, description, rent_amount, rent_due, privacy_option, mod_approved, last_updated, time_claimed, rejection_reason, reputation, zone_id, performance_cost) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                    (
                        prop_dict["id"],
                        prop_dict["owner_id"],
                        prop_dict["template_id"],
                        prop_dict["clone_id"],
                        prop_dict["name"],
                        prop_dict["description"],
                        prop_dict["rent_amount"],
                        prop_dict["rent_due"],
                        prop_dict["privacy_option"],
                        prop_dict["mod_approved"],
                        prop_dict["last_updated"],
                        prop_dict["time_claimed"],
                        prop_dict["rejection_reason"],
                        prop_dict["reputation"],
                        prop_dict["zone_id"],
                        prop_dict["performance_cost"]
                    )
                )
                nu_db_connection.commit()
                print(f"{self._MODULE_NAME} {MIGRATION_TAG}: Successfully migrated property ID [{old_prop_id}] to NU as [{prop_dict['id']}]")

                # Cycle through the properties_contents table to find the property contents for this property and update
                blu_db_cursor.execute('SELECT * FROM properties_contents WHERE property_id=%s', (old_prop_id,))
                prop_contents = blu_db_cursor.fetchall()
                if not prop_contents:
                    print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: No property contents found for BLU property ID [{old_prop_id}]. Skipping property migration.")
                else:
                    for prop_content in prop_contents:
                        content_dict = {
                            "id": prop_content[0],
                            "property_id": prop_content[1],
                            "ugc_id": prop_content[2],
                            "lot": prop_content[3],
                            "x": prop_content[4],
                            "y": prop_content[5],
                            "z": prop_content[6],
                            "rx": prop_content[7],
                            "ry": prop_content[8],
                            "rz": prop_content[9],
                            "rw": prop_content[10],
                            "model_name": prop_content[11],
                            "model_description": prop_content[12],
                            "behavior_1": prop_content[13],
                            "behavior_2": prop_content[14],
                            "behavior_3": prop_content[15],
                            "behavior_4": prop_content[16],
                            "behavior_5": prop_content[17],
                        }

                        # Update ugc id if needed
                        if content_dict["ugc_id"] is not None:
                            # Generate a new UGC ID for the NU database
                            count = 0
                            while True:
                                new_ugc_id = random.randint(1, 2_147_483_647)
                                nu_db_cursor.execute('SELECT id FROM ugc WHERE id=%s', (new_ugc_id,))
                                count += 1
                                if not nu_db_cursor.fetchone():
                                    break
                                elif count >= 2_147_483_647:
                                    raise self.ObjectIDRangeError(f"Unable to generate a new UGC ID for property content {content_dict['id']} as all IDs are in use.")

                            # Get UGC data for this content
                            blu_db_cursor.execute('SELECT * FROM ugc WHERE id=%s', (content_dict["ugc_id"],))
                            ugc_data = blu_db_cursor.fetchall()
                            if not ugc_data:
                                print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: No UGC data found for BLU UGC ID [{content_dict['ugc_id']}]. Skipping property content migration.")
                                continue

                            # Cycle through each ugc and migrate it to the NU database
                            for ugc in ugc_data:
                                # Extract UGC data
                                ugc_dict = {
                                    "id": ugc[0],
                                    "account_id": ugc[1],
                                    "character_id": ugc[2],
                                    "is_optimized": ugc[3],
                                    "lxfml": ugc[4],
                                    "bake_ao": ugc[5],
                                    "filename": ugc[6]
                                }

                                # Update the id with the new UGC ID
                                old_ugc_id = ugc_dict["id"]  # Store the old UGC ID for logging
                                ugc_dict["id"] = new_ugc_id

                                # Update the account_id with the NU account ID
                                ugc_dict["account_id"] = nu_account_id

                                # Update the character_id with the new character ID
                                ugc_dict["character_id"] = new_character_id

                                # Insert the UGC data into the NU database with the new UGC ID
                                nu_db_cursor.execute(
                                    'INSERT INTO ugc (id, account_id, character_id, is_optimized, lxfml, bake_ao, filename) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                                    (
                                        ugc_dict["id"],
                                        ugc_dict["account_id"],
                                        ugc_dict["character_id"],
                                        ugc_dict["is_optimized"],
                                        ugc_dict["lxfml"],
                                        ugc_dict["bake_ao"],
                                        ugc_dict["filename"]
                                    )
                                )
                                nu_db_connection.commit()
                                print(f"{self._MODULE_NAME} {MIGRATION_TAG}: Successfully migrated UGC ID [{old_ugc_id}] to NU as [{ugc_dict['id']}]")
                        
                            # Update the ugc id in the property content
                            content_dict["ugc_id"] = new_ugc_id

                        # Update the property id 
                        content_dict["property_id"] = new_id

                        # Update the content id with a new ID
                        old_content_id = content_dict["id"]  # Store the old content ID for logging
                        content_dict["id"] = self._generate_item_id()

                        # Insert the property content into the NU database with the new content ID
                        nu_db_cursor.execute(
                            'INSERT INTO properties_contents (id, property_id, ugc_id, lot, x, y, z, rx, ry, rz, rw, model_name, model_description, behavior_1, behavior_2, behavior_3, behavior_4, behavior_5) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                            (
                                content_dict["id"],
                                content_dict["property_id"],
                                content_dict["ugc_id"],
                                content_dict["lot"],
                                content_dict["x"],
                                content_dict["y"],
                                content_dict["z"],
                                content_dict["rx"],
                                content_dict["ry"],
                                content_dict["rz"],
                                content_dict["rw"],
                                content_dict["model_name"],
                                content_dict["model_description"],
                                content_dict["behavior_1"],
                                content_dict["behavior_2"],
                                content_dict["behavior_3"],
                                content_dict["behavior_4"],
                                content_dict["behavior_5"]
                            )
                        )
                        nu_db_connection.commit()
                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: Successfully migrated property content ID [{old_content_id}] to NU as ID [{content_dict['id']}] for property {content_dict['property_id']}")

        finally:
            if nu_db_cursor:
                nu_db_cursor.close()
            if blu_db_cursor:
                blu_db_cursor.close()

            if nu_db_connection:
                nu_db_connection.close()
            if blu_db_connection:
                blu_db_connection.close()

    def _migrate_ugc_modular(self, blu_character_id, new_character_id):
        """
        Migrates UGC modular builds from the BLU character to a NU character.

        Parameters:
            blu_character_id (int): The BLU character ID whose UGC modular builds will be migrated.
            new_character_id (int): The new character ID in the NU database where UGC modular builds will be applied.

        Returns:
            ugc_id_pairs (list): List of tuples (old_ugc_id, new_ugc_id) for migrated builds.

        Raises:
            DatabaseConnectionError: If a database connection cannot be established.
        """
        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: INFO: Migrating UGC modular builds from BLU character {blu_character_id} to NU character {new_character_id} ...")

        nu_db_connection = self._get_db_connection()
        blu_db_connection = self._get_blu_db_connection()
        if not nu_db_connection or not blu_db_connection:
            raise self.DatabaseConnectionError("No database connection available for migrating UGC modular builds.")
        
        nu_db_cursor = nu_db_connection.cursor()
        blu_db_cursor = blu_db_connection.cursor()

        ugc_id_pairs = [] # List to store pairs of old and new UGC IDs

        try:
            blu_db_cursor.execute('SELECT * FROM ugc_modular_build WHERE character_id = %s', (blu_character_id,))
            ugc_modular_builds = blu_db_cursor.fetchall()

            for build in ugc_modular_builds:
                modular_build = {
                   "ugc_id": build[0],
                   "character_id": build[1],
                   "ldf_config": build[2]
                }

                # Update the character id
                modular_build["character_id"] = new_character_id

                # Generate a new UGC ID for the NU database
                new_id = self._generate_item_id()
                old_ugc_id = modular_build["ugc_id"]

                # Update the ugc id
                modular_build["ugc_id"] = new_id

                ugc_id_pairs.append((old_ugc_id, new_id))  

                # Insert the modular build into the NU database
                nu_db_cursor.execute(
                    'INSERT INTO ugc_modular_build (ugc_id, character_id, ldf_config) VALUES (%s, %s, %s)',
                    (
                        modular_build["ugc_id"],
                        modular_build["character_id"],
                        modular_build["ldf_config"]
                    )
                )
                nu_db_connection.commit()
                print(f"{self._MODULE_NAME} {MIGRATION_TAG}: Successfully migrated UGC modular build UGC ID [{old_ugc_id}] to NU as ID [{modular_build['ugc_id']}]")

            print(f"{self._MODULE_NAME} {MIGRATION_TAG}: Successfully migrated UGC modular builds from BLU character {blu_character_id} to NU character {new_character_id}")

            return ugc_id_pairs

        finally:
            if nu_db_cursor:
                nu_db_cursor.close()
            if blu_db_cursor:
                blu_db_cursor.close()

            if nu_db_connection:
                nu_db_connection.close()
            if blu_db_connection:
                blu_db_connection.close()

    def _main_migration_loop(self):
        """
        Main migration loop that processes users in the migration queue and performs necessary actions.

        Continuously checks for users in the migration queue, retrieves their information,
        and performs the migration process for each user until the queue is empty.

        Parameters:
            None

        Returns:
            None
        """
        print(f"{self._MODULE_NAME}: Starting main migration loop...")

        nu_db_connection = None
        blu_db_connection = None
        nu_db_cursor = None

        global MIGRATION_TAG
        MIGRATION_TAG = "[migration]"

        while(True):
           if not self.migration_queue.empty():
                try:
                    # Setup the DB connections
                    nu_db_connection = self._get_db_connection()
                    if not nu_db_connection:
                        print(f"{self._MODULE_NAME}: ERROR: No DB connection available for migration loop")
                        return
                    
                    blu_db_connection = self._get_blu_db_connection()
                    if not blu_db_connection:
                        print(f"{self._MODULE_NAME}: ERROR: No DB connection available for migration loop")
                        return
                    
                    nu_db_cursor = nu_db_connection.cursor()

                    # Check if there are any duplicate ugc_ids in ugc_modular_build table
                    nu_db_cursor.execute('SELECT ugc_id, COUNT(*) FROM ugc_modular_build GROUP BY ugc_id HAVING COUNT(*) > 1')
                    duplicate_results = nu_db_cursor.fetchall()
                    if duplicate_results:
                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: Found duplicate ugc_ids in ugc_modular_build table:")
                        for dup in duplicate_results:
                            print(f"UGC ID: {dup[0]}, Count: {dup[1]}")
                        raise self.ObjectIDRangeError("Duplicate UGC IDs found in ugc_modular_build table. Please resolve duplicates before proceeding with migration.")
                    
                    # Check if there are any duplicate item IDs in properties_contents table
                    nu_db_cursor.execute('SELECT id, COUNT(*) FROM properties_contents GROUP BY id HAVING COUNT(*) > 1')
                    duplicate_results = nu_db_cursor.fetchall()
                    if duplicate_results:
                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: Found duplicate IDs in properties_contents table:")
                        for dup in duplicate_results:
                            print(f"Item ID: {dup[0]}, Count: {dup[1]}")
                        raise self.ObjectIDRangeError("Duplicate item IDs found in properties_contents table. Please resolve duplicates before proceeding with migration.")
                    nu_db_cursor.close()

                    # Get all item IDs from the database
                    print(f"{self._MODULE_NAME}: INFO: Updating local copy of all item IDs in the database...")
                    self.used_item_ids = self._get_all_item_ids(nu_db_connection)

                    # Get the next migration request from the queue
                    migration_request = self.migration_queue.get()

                    discord_uuid = migration_request["discord_uuid"]
                    print(f"{self._MODULE_NAME}: Processing migration request for user {discord_uuid}")

                    # Set the transfer state for the user to TRANSFER_IN_PROGRESS
                    self._set_user_transfer_state(discord_uuid, self.migration_state.TRANSFER_IN_PROGRESS)

                    MIGRATION_TAG = f"[migration {discord_uuid}]"

                    # Get the migration info for the user
                    nu_db_cursor = nu_db_connection.cursor()
                    nu_db_cursor.execute('SELECT * FROM blu_transfers WHERE discord_uuid=%s', (discord_uuid,))
                    result = nu_db_cursor.fetchone()
                    if not result:
                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: ERROR: No migration entry found for user {discord_uuid} when executing transfer. Skipping...")
                        continue

                    nu_account_id = result[2]
                    blu_account_id = result[3]
                    migration_state = result[4]
                    chosen_characters = json.loads(result[6]) if result[6] else None # Will be None if we are not doing selective migration

                    #############################################
                    # Migration Handling
                    #############################################

                    if migration_request["selective_migration"]:
                        chars_to_delete = chosen_characters["delete_nu"]
                        chars_to_migrate = chosen_characters["migrate_blu"]

                        # Delete the characters in NU that the user has chosen to delete
                        for char_id in chars_to_delete:
                            # Delete the character from the NU database
                            self._delete_character(char_id)
                            print(f"{self._MODULE_NAME} {MIGRATION_TAG}: Successfully deleted character with ID {char_id} from NU for user {discord_uuid}")

                    else:
                        # If selective migration is not enabled, migrate over all BLU characters
                        blu_characters = self._get_BLU_characters(blu_account_id)

                        chars_to_delete = []
                        chars_to_migrate = [char[1] for char in blu_characters]  # Get the character IDs from the BLU characters

                    char_map = []
                    for char_id in chars_to_migrate:

                        blu_name = self._get_BLU_character_name(char_id)

                        # Create a new character in NU for the BLU character to transfer on top of
                        new_char_id = self._create_new_character(discord_uuid, nu_account_id)

                        # Migrate the properties and UGC from the BLU character to the NU character
                        self._migrate_properties(nu_account_id, char_id, new_char_id)

                        # Migrate the UGC modular builds (rockets, cars, etc) from the BLU character to the NU character
                        ugc_id_pairs = self._migrate_ugc_modular(char_id, new_char_id)

                        # Pull and clean the character XML from BLU
                        cleaned_xml = self._pull_and_clean_char_xml(char_id, new_char_id, ugc_id_pairs)

                        # Insert the cleaned XML into the NU database
                        nu_db_cursor.execute('UPDATE charxml SET xml_data=%s WHERE id=%s', (cleaned_xml, new_char_id))
                        nu_db_connection.commit()
                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: Successfully migrated character [{char_id}] to NU with new ID [{new_char_id}] for user {discord_uuid}")
                        char_map.append((blu_name, new_char_id))

                    # Set the transfer state for the user to COMPLETED
                    self._set_user_transfer_state(discord_uuid, self.migration_state.COMPLETED)

                    # Unlock the user account
                    self._unlock_account("", discord_uuid, False)

                    # Send message to user that migration is complete
                    user = self._bot.get_user(int(discord_uuid))
                    if user:
                        lines = ["**Your BLU -> NU migration is complete!**"]
                        if char_map:
                            lines.append("")
                            lines.append("**Character Mapping:**")
                            for name, nid in char_map:
                                lines.append(f"- {name} -> `{nid}`")
                        lines.append("\nIf you have any issues, please contact a Mythran.")
                        notification_message = "\n".join(lines)
                        coroutine = user.send(notification_message)
                        asyncio.run_coroutine_threadsafe(coroutine, self._bot.loop)
                    else:
                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: User {discord_uuid} not found. Unable to send migration completion message.")
                
                
                ############################################
                # Exception Handling
                ############################################
                except self.CorruptCharacterXML as e:
                    # Log the error and update the database
                    print(f"{self._MODULE_NAME} {MIGRATION_TAG}: ERROR: {e.message}")
                    self._set_user_transfer_state(discord_uuid, self.migration_state.ERROR_STATE, 6)

                    # Send message to bot channel that migration failed
                    bot_channel = discord.utils.get(self._bot.get_all_channels(), name=BOT_CHANNEL)
                    if bot_channel:
                        coroutine = bot_channel.send(f"**Migration failed for user `{discord_uuid}`**\n\nError: {e.message}")
                        asyncio.run_coroutine_threadsafe(coroutine, self._bot.loop)
                    else:
                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: Bot channel not found. Unable to send migration failure message.")
                    continue

                except self.ObjectIDRangeError as e:
                    # Log the error and update the database
                    print(f"{self._MODULE_NAME} {MIGRATION_TAG}: ERROR: {e.message} Object ID: {e.object_id}")
                    self._set_user_transfer_state(discord_uuid, self.migration_state.ERROR_STATE, 3)

                    # Send message to bot channel that migration failed
                    bot_channel = discord.utils.get(self._bot.get_all_channels(), name=BOT_CHANNEL)
                    if bot_channel:
                        coroutine = bot_channel.send(f"**Migration failed for user `{discord_uuid}`**\n\nError: {e.message} Object ID: {e.object_id}")
                        asyncio.run_coroutine_threadsafe(coroutine, self._bot.loop)
                    else:
                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: Bot channel not found. Unable to send migration failure message.")    
                    continue

                except self.DatabaseConnectionError as e:
                    print(f"{self._MODULE_NAME} {MIGRATION_TAG}: ERROR: {e.message}")

                    # Dont log to the database as we are unable to connect to it

                    # Send message to bot channel that migration failed
                    bot_channel = discord.utils.get(self._bot.get_all_channels(), name=BOT_CHANNEL)
                    if bot_channel:
                        coroutine = bot_channel.send(f"**Migration failed for user `{discord_uuid}`**\n\nError: {e.message}")
                        asyncio.run_coroutine_threadsafe(coroutine, self._bot.loop)
                    else:
                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: Bot channel not found. Unable to send migration failure message.")
                    continue

                except self.DatabaseFetchError as e:
                    print(f"{self._MODULE_NAME} {MIGRATION_TAG}: ERROR: {e.message}")
                    self._set_user_transfer_state(discord_uuid, self.migration_state.ERROR_STATE, 4)

                    # Send message to bot channel that migration failed
                    bot_channel = discord.utils.get(self._bot.get_all_channels(), name=BOT_CHANNEL)
                    if bot_channel:
                        coroutine = bot_channel.send(f"**Migration failed for user `{discord_uuid}`**\n\nError: {e.message}")
                        asyncio.run_coroutine_threadsafe(coroutine, self._bot.loop)
                    else:
                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: Bot channel not found. Unable to send migration failure message.")    
                    continue

                except self.NoAvailableCharacterSlotsError as e:
                    print(f"{self._MODULE_NAME} {MIGRATION_TAG}: ERROR: {e.message}")
                    self._set_user_transfer_state(discord_uuid, self.migration_state.ERROR_STATE, 5)

                    # Send message to bot channel that migration failed
                    bot_channel = discord.utils.get(self._bot.get_all_channels(), name=BOT_CHANNEL)
                    if bot_channel:
                        coroutine = bot_channel.send(f"**Migration failed for user `{discord_uuid}`**\n\nError: {e.message}")
                        asyncio.run_coroutine_threadsafe(coroutine, self._bot.loop)
                    else:
                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: Bot channel not found. Unable to send migration failure message.")    
                    continue

                except Exception as e:
                    try:
                        self._set_user_transfer_state(discord_uuid, self.migration_state.ERROR_STATE, 9)

                        # Send message to bot channel that migration failed
                        bot_channel = discord.utils.get(self._bot.get_all_channels(), name=BOT_CHANNEL)
                        if bot_channel:
                            coroutine = bot_channel.send(f"**Migration failed for user `{discord_uuid}`**\n\nError: {e.message}")
                            asyncio.run_coroutine_threadsafe(coroutine, self._bot.loop)
                        else:
                            print(f"{self._MODULE_NAME} {MIGRATION_TAG}: WARNING: Bot channel not found. Unable to send migration failure message.")  
                    except Exception as e2:
                        print(f"{self._MODULE_NAME} {MIGRATION_TAG}: ERROR: Failed to send migration failure message to bot channel: {str(e2)}")  

                    print(f"{self._MODULE_NAME} {MIGRATION_TAG}: ERROR: An unexpected error occurred during migration: {str(e)}")

                finally:
                    if nu_db_cursor:
                        nu_db_cursor.close()
                    if nu_db_connection:
                        nu_db_connection.close()
                    if blu_db_connection:
                        blu_db_connection.close()

                    MIGRATION_TAG = "[migration]"
            
           else:
                time.sleep(5)

'''
migration_struct = {
    "discord_uuid": "123456789", # The Discord UUID of the user
    "selective_migration": False,  # If True, only migrate specific characters
}
'''