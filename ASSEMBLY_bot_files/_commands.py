import asyncio
import discord
import json
import os
import time
from openai import OpenAI
from ASSEMBLY_bot_files.ASSEMBLY_botSettings import COMMAND_ROLE, BOT_CHANNEL, WHITELIST_CHANNEL, WHITELIST_FILE, GPT_API_KEY

class BotCommands():
    def __init__(self):
        super().__init__()

    def _setup_commands(self):
        """
        Register command handlers onto self._bot
        """

        # Ensure self._bot is initialized
        if not hasattr(self, '_bot') or self._bot is None:
            raise AttributeError("self._bot is not initialized. Ensure it is set before calling _setup_commands.")

        ##############
        # Command: lockaccount
        ##############
        @self._bot.tree.command(name="lockaccount", description="Lock the account of a user")
        @discord.app_commands.describe(identifier="The username or key of the user")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _lock_account_cmd(interaction: discord.Interaction, identifier: str):
            # Check if the identifier is a play key
            if self._is_playkey(identifier):
                uuid = self._get_user_id_from_key(identifier)
                
                if uuid:
                    user = discord.utils.get(interaction.guild.members, id=int(uuid))
                else:
                    await interaction.response.send_message(f'User with name/play-key `{identifier}` not found', ephemeral=True)
                    return
            else:
                user = discord.utils.get(interaction.guild.members, name=identifier)
            
            if user:
                message = self._lock_account(user.name, user.id, False)
                await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.response.send_message(f'User with name/play-key `{identifier}` not found', ephemeral=True)

        @_lock_account_cmd.error
        async def _lock_account_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: unlockaccount
        ##############
        @self._bot.tree.command(name="unlockaccount", description="Unlock the account of a user")
        @discord.app_commands.describe(identifier="The username or key of the user")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _unlock_account_cmd(interaction: discord.Interaction, identifier: str):
            # Check if the identifier is a play key
            if self._is_playkey(identifier):
                uuid = self._get_user_id_from_key(identifier)
                
                if uuid:
                    user = discord.utils.get(interaction.guild.members, id=int(uuid))
                else:
                    await interaction.response.send_message(f'User with name/play-key `{identifier}` not found', ephemeral=True)
                    return
            else:
                user = discord.utils.get(interaction.guild.members, name=identifier)

            if user:
                message = self._unlock_account(user.name, user.id)
                await interaction.response.send_message(message, ephemeral=True)          
            else:
                await interaction.response.send_message(f'User with name/play-key `{identifier}` not found', ephemeral=True)

        @_unlock_account_cmd.error
        async def _unlock_account_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: addnote
        ##############
        @self._bot.tree.command(name="addnote", description="Add a note to a user's record")
        @discord.app_commands.describe(username="The username of the user", note="The note to add")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _add_note_cmd(interaction: discord.Interaction, username: str, note: str):
            # Attempt to find the user in the guild by their username
            user = discord.utils.get(interaction.guild.members, name=username)
            if user:
                # Create a note object
                note_obj = {"timestamp": int(time.time()), "note": note}

                # Save the note to the database
                if self._save_record_entry(str(user.id), self.record_type.NOTE, note_obj):
                    # Successfully added the note, send confirmation to the user
                    await interaction.response.send_message(f'Note added for {username}: {note}', ephemeral=True)
                else:
                    # No play key found for the user, notify the user
                    await interaction.response.send_message(f'No play key found for user `{username}`', ephemeral=True)
            else:
                # User not found in the guild, notify the user
                await interaction.response.send_message(f'User `{username}` not found', ephemeral=True)

        @_add_note_cmd.error
        async def _add_note_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: addoffense
        ##############
        @self._bot.tree.command(name="addoffense", description="Add an offense to a user's record")
        @discord.app_commands.describe(username="The username of the user", offense_type="The type of offense (e.g., Name, Chat, Property)", offense="The offense description", action_taken="Action taken for the offense")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _add_offense_cmd(interaction: discord.Interaction, username: str, offense_type: str, offense: str, action_taken: str):
            # Attempt to find the user in the guild by their username
            user = discord.utils.get(interaction.guild.members, name=username)
            if user:
                # Create an offense object
                offense_obj = {
                    "timestamp": int(time.time()),
                    "type": offense_type,
                    "offense": offense,
                    "action-taken": action_taken,
                    "mod-notified": True # Set to true since a mod is adding the offense
                }

                # Save the offense to the database
                if self._save_record_entry(str(user.id), self.record_type.OFFENSE, offense_obj):
                    # Successfully added the offense, send confirmation to the user
                    await interaction.response.send_message(f'Offense added for {username}: {offense}', ephemeral=True)

                    # Log the addition
                    guild = user.guild
                    botMessageChannel = discord.utils.get(guild.text_channels, name=BOT_CHANNEL)
                    if botMessageChannel:
                        await botMessageChannel.send(f'A record was added to the `OFFENSE` category for user `{username}` by `{interaction.user}`.\nDetails of the added record:\n  `{offense_obj}`')
                    else:
                        # Log the message to the console
                        print(f"{self._MODULE_NAME}: A record was added to the `OFFENSE` category for user `{username}` by `{interaction.user}`.\nDetails of the added record:\n  `{offense_obj}`")
                else:
                    # No play key found for the user, notify the user
                    await interaction.response.send_message(f'No play key found for user `{username}`', ephemeral=True)
            else:
                # User not found in the guild, notify the user
                await interaction.response.send_message(f'User `{username}` not found', ephemeral=True)

        @_add_offense_cmd.error
        async def _add_offense_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: addwarning
        ##############
        @self._bot.tree.command(name="addwarning", description="Add a warning to a user's record")
        @discord.app_commands.describe(username="The username of the user", reason="The reason for the warning")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _add_warning_cmd(interaction: discord.Interaction, username: str, reason: str):
            # Attempt to find the user in the guild by their username
            user = discord.utils.get(interaction.guild.members, name=username)
            if user:
                # Create a warning object
                warning_obj = {
                    "timestamp": int(time.time()),
                    "reason": reason
                }

                # Save the warning to the database
                if self._save_record_entry(str(user.id), self.record_type.WARNING, warning_obj):
                    # Successfully added the warning, send confirmation to the user
                    await interaction.response.send_message(f'Warning added for {username}: {reason}', ephemeral=True)

                    # Log the addition
                    guild = user.guild
                    botMessageChannel = discord.utils.get(guild.text_channels, name=BOT_CHANNEL) 
                    if botMessageChannel:
                        await botMessageChannel.send(f'A record was added to the `WARNING` category for user `{username}` by `{interaction.user}`.\nDetails of the added record:\n  `{warning_obj}`')
                    else:
                        # Log the message to the console
                        print(f"{self._MODULE_NAME}: A record was added to the `WARNING` category for user `{username}` by `{interaction.user}`.\nDetails of the added record:\n  `{warning_obj}`")

                else:
                    # No play key found for the user, notify the user
                    await interaction.response.send_message(f'No play key found for user `{username}`', ephemeral=True)
            else:
                # User not found in the guild, notify the user
                await interaction.response.send_message(f'User `{username}` not found', ephemeral=True)

        @_add_warning_cmd.error
        async def _add_warning_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: displayrecords
        ##############
        @self._bot.tree.command(name="displayrecords", description="Display records for a user")
        @discord.app_commands.describe(username="The username of the user", record="The type of record to display")
        @discord.app_commands.choices(record=[
            discord.app_commands.Choice(name="All",     value=self.record_type.ALL),
            discord.app_commands.Choice(name="Note",    value=self.record_type.NOTE),
            discord.app_commands.Choice(name="Offense", value=self.record_type.OFFENSE),
            discord.app_commands.Choice(name="Warning", value=self.record_type.WARNING),
        ])
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _display_records_cmd(interaction: discord.Interaction, record: int, username: str):
            db_connection = self._get_db_connection()

            if not db_connection:
                await interaction.response.send_message("No mysql connection, unable to display records", ephemeral=True)
                return

            user = discord.utils.get(interaction.guild.members, name=username)
            if user:
                uuid_str = str(user.id)
                cursor = db_connection.cursor()
                cursor.execute('SELECT notes FROM play_keys WHERE discord_uuid=%s', (uuid_str,))
                result = cursor.fetchone()

                if result:
                    # Format the records for display
                    notes_display, offenses_display, warnings_display = self._format_user_records(result[0])
                    
                    if record == self.record_type.ALL:
                        notes_display = f"{notes_display}\n\n{offenses_display}\n\n{warnings_display}"
                        await interaction.response.send_message(f'Records for `{username}`:\n\n{notes_display}', ephemeral=True)
                    
                    elif record == self.record_type.NOTE:
                        await interaction.response.send_message(f'Notes for `{username}`:\n\n{notes_display}', ephemeral=True)

                    elif record == self.record_type.OFFENSE:
                        await interaction.response.send_message(f'Offenses for `{username}`:\n\n{offenses_display}', ephemeral=True)

                    elif record == self.record_type.WARNING:
                        await interaction.response.send_message(f'Warnings for `{username}`:\n\n{warnings_display}', ephemeral=True)
                else:
                    await interaction.response.send_message(f'No play key found for user {username}', ephemeral=True)
            else:
                await interaction.response.send_message(f'User {username} not found', ephemeral=True)

            cursor.close()
            db_connection.close()

        @_display_records_cmd.error
        async def _display_records_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: showkey
        ##############
        @self._bot.tree.command(name="showkey", description="Show play key for a user")
        @discord.app_commands.describe(username="The username of the user")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _show_key_cmd(interaction: discord.Interaction, username: str):
            user = discord.utils.get(interaction.guild.members, name=username)
            if user:
                key = self._get_key_from_user_id(user.id)

                if key:
                    await interaction.response.send_message(f'Play key for {username}: {key}', ephemeral=True)
                else:
                    await interaction.response.send_message(f'No play key found for user {username}', ephemeral=True)
            else:
                await interaction.response.send_message(f'User {username} not found', ephemeral=True)

        @_show_key_cmd.error
        async def _show_key_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: showaccount
        ##############
        @self._bot.tree.command(name="showaccount", description="Show Discord account name tied to a play key")
        @discord.app_commands.describe(key="The play key to look up")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _show_account_cmd(interaction: discord.Interaction, key: str):
            uuid = self._get_user_id_from_key(key)

            if uuid:
                user = discord.utils.get(interaction.guild.members, id=int(uuid))
                if user:
                    await interaction.response.send_message(f'Account name for play key `{key}`: `{user.name}`', ephemeral=True)
                else:
                    await interaction.response.send_message(f'No account found for uuid: `{uuid}`', ephemeral=True)
            else:
                await interaction.response.send_message(f'No account found for play key: `{key}`', ephemeral=True)

        @_show_account_cmd.error
        async def _show_account_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: removerecord
        ##############
        @self._bot.tree.command(name="removerecord", description="Remove a record from a user by ID")
        @discord.app_commands.describe(username="The username of the user", record="Record catagory to removed from", record_id="The ID of the record to remove")
        @discord.app_commands.choices(record=[
            discord.app_commands.Choice(name="Note",    value=self.record_type.NOTE),
            discord.app_commands.Choice(name="Offense", value=self.record_type.OFFENSE),
            discord.app_commands.Choice(name="Warning", value=self.record_type.WARNING),
        ])
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _remove_record_cmd(interaction: discord.Interaction, username: str, record: int, record_id: int):
            db_connection = self._get_db_connection()

            if not db_connection:
                await interaction.response.send_message("No mysql connection, unable to remove record", ephemeral=True)
                return

            user = discord.utils.get(interaction.guild.members, name=username)
            if user:
                uuid_str = str(user.id)
                cursor = db_connection.cursor()
                cursor.execute('SELECT notes FROM play_keys WHERE discord_uuid=%s', (uuid_str,))
                result = cursor.fetchone()

                if result:
                    records = json.loads(result[0]) if result[0] else {"notes": [], "offenses": [], "warnings": []}
                    record_key = None

                    # Determine the record category
                    if record == self.record_type.NOTE:
                        record_key = "notes"
                    elif record == self.record_type.OFFENSE:
                        record_key = "offenses"
                    elif record == self.record_type.WARNING:
                        record_key = "warnings"

                    if record_key is None or record_id < 0 or record_id >= len(records[record_key]):
                        await interaction.response.send_message(f'Record with ID `{record_id}` does not exist in category `{record_key}` for `{username}`', ephemeral=True)
                        cursor.close()
                        db_connection.close()
                        return

                    # Remove the record by its index
                    removed_record = records[record_key].pop(record_id)

                    # Update the database
                    cursor.execute('UPDATE play_keys SET notes=%s WHERE discord_uuid=%s', (json.dumps(records), uuid_str))
                    db_connection.commit()
                    cursor.close()
                    db_connection.close()
                    await interaction.response.send_message(f'Record with ID `{record_id}` removed from category `{record_key}` for `{username}`', ephemeral=True)

                    # Log the removal
                    guild = user.guild
                    botMessageChannel = discord.utils.get(guild.text_channels, name=BOT_CHANNEL) 
                    if botMessageChannel:
                        await botMessageChannel.send(f'Note with ID `{record_id}` removed from category `{record_key}` for user `{username}` by `{interaction.user}`\nRemoved record:\n  `{removed_record}`')
                    else:
                        # Log the message to the console
                        print(f"{self._MODULE_NAME}: Note with ID `{record_id}` removed from category `{record_key}` for user `{username}` by `{interaction.user}`\nRemoved record:\n  `{removed_record}`")
                else:
                    await interaction.response.send_message(f'No play key found for user `{username}`', ephemeral=True)
            else:
                await interaction.response.send_message(f'User `{username}` not found', ephemeral=True)

        @_remove_record_cmd.error
        async def _remove_record_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)

        
        ##############
        # Command: updatewhitelist
        ##############
        @self._bot.tree.command(name="updatewhitelist", description="Update the whitelist for a user")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _update_whitelist_cmd(interaction: discord.Interaction):
            try:
                # Ensure path to whitelist is valid
                if not os.path.exists(WHITELIST_FILE):
                    print(f"{self._MODULE_NAME}: ERROR: Whitelist file `{WHITELIST_FILE}` not found.")
                    await interaction.response.send_message(f"Whitelist file `{WHITELIST_FILE}` not found.", ephemeral=True)
                    return
                
                # Ensure the whitelist file is readable
                if not os.access(WHITELIST_FILE, os.R_OK):
                    print(f"{self._MODULE_NAME}: ERROR: Whitelist file `{WHITELIST_FILE}` is not readable.")
                    await interaction.response.send_message(f"Whitelist file `{WHITELIST_FILE}` is not readable.", ephemeral=True)
                
                # Ensure the whitelist file is writable
                if not os.access(WHITELIST_FILE, os.W_OK):
                    print(f"{self._MODULE_NAME}: ERROR: Whitelist file `{WHITELIST_FILE}` is not writable.")
                    await interaction.response.send_message(f"Whitelist file `{WHITELIST_FILE}` is not writable.", ephemeral=True)
                    return
    
                # Ensure the whitelist channel exists
                guild = interaction.guild
                whitelist_channel = discord.utils.get(guild.text_channels, name=WHITELIST_CHANNEL)
                if not whitelist_channel:
                    await interaction.response.send_message(f"Whitelist channel `{WHITELIST_CHANNEL}` not found.", ephemeral=True)
                    return

                # grab all messages into a list
                messages = []
                async for msg in whitelist_channel.history(limit=None):
                    messages.append(msg)

                # Process the messages to update the whitelist
                whitelist_data = []
                for message in messages:
                    content = message.content.strip()
                    if content:
                        whitelist_data.append(content)
                
                if not whitelist_data:
                    await interaction.response.send_message("No valid whitelist data found in the channel.", ephemeral=True)
                    return
                
                await interaction.response.send_message("Processing... This could take a few minutes...", ephemeral=True)

                # Convert the whitelist data into a new line separated string
                whitelist_data = '\n'.join(whitelist_data)

                # Initialize OpenAI API client
                openAIClient = OpenAI(api_key=GPT_API_KEY)

                # Send the whitelist data to GPT for processing
                gpt_response = self._send_to_gpt(openAIClient, whitelist_data)

                # Close the connection
                openAIClient.close()

                # Parse the JSON response from GPT
                try:
                    processed_whitelist = json.loads(gpt_response)
                except json.JSONDecodeError as e:
                    print(f"{self._MODULE_NAME}: ERROR decoding GPT response: {e}")
                    await interaction.response.send_message(f"Error decoding GPT response: {e}", ephemeral=True)
                    return

                # Read the existing whitelist data from the file
                existing_whitelist = set()
                if os.path.exists(WHITELIST_FILE):
                    with open(WHITELIST_FILE, 'r') as f:
                        existing_whitelist = set(line.strip() for line in f if line.strip())

                # Add only new entries to the whitelist (no duplicates)
                new_entries = [entry for entry in processed_whitelist if entry not in existing_whitelist]
                if new_entries:
                    with open(WHITELIST_FILE, 'a') as f:
                        f.write('\n'.join(new_entries) + '\n')

                print(f"{self._MODULE_NAME}: Added {len(new_entries)} new entries to whitelist file `{WHITELIST_FILE}`")

                # Delete all messages in the whitelist channel using bulk delete
                await whitelist_channel.purge(limit=None, bulk=False) # bulk=False forces individual deletes (no 14‑day cutoff)
                
                print(f"{self._MODULE_NAME}: Deleted {len(messages)} messages from whitelist channel `{WHITELIST_CHANNEL}`")

                # Delete the .dcf file if it exists
                dcf_file = WHITELIST_FILE.replace('.txt', '.dcf')
                if os.path.exists(dcf_file):
                    os.remove(dcf_file)
                    print(f"{self._MODULE_NAME}: Deleted whitelist dcf file `{dcf_file}`")

                await interaction.edit_original_response(content=f"Whitelist updated successfully. Added {len(new_entries)} new entries.\nPlease reboot the server")

            except FileNotFoundError as e:
                print(f"{self._MODULE_NAME}: ERROR: Whitelist file not found: {e}")
                await interaction.response.send_message(f"Whitelist file not found: {e}", ephemeral=True)
                return
            except discord.HTTPException as e:
                print(f"{self._MODULE_NAME}: ERROR: Discord API error: {e}")
                await interaction.response.send_message(f"Discord API error: {e}", ephemeral=True)
                return
            except Exception as e:
                print(f"{self._MODULE_NAME}: Unexpected error updating whitelist: {e}")
                await interaction.response.send_message(f"Unexpected error updating whitelist: {e}", ephemeral=True)
                return

        @_update_whitelist_cmd.error
        async def _update_whitelist_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: sendgameannouncement
        ##############
        @self._bot.tree.command(name="sendgameannouncement", description="Send an announcement to the game")
        @discord.app_commands.describe(title="The title of the announcement", message="The message of the announcement")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _send_game_announcement_cmd(interaction: discord.Interaction, title: str, message: str):
            # Make the request to send the announcement
            response = self._make_game_announcement(title, message)

            await interaction.response.send_message(response, ephemeral=True)

        @_send_game_announcement_cmd.error
        async def _send_game_announcement_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: gameannounceupdate
        ##############
        @self._bot.tree.command(name="gameannounceupdate", description="Update the game announcement")
        @discord.app_commands.describe(minutes_to_update="Number of minutes until server shutdown")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _game_announce_update_cmd(interaction: discord.Interaction, minutes_to_update: int):
            # Make the request to update the announcement
            response = self._make_game_announcement(title=f"Server shutting down in {minutes_to_update} minutes!", message=f"Server will shutdown in {minutes_to_update} minutes for updates. See Discord for more info.")

            await interaction.response.send_message(response, ephemeral=True)
        
        @_game_announce_update_cmd.error
        async def _game_announce_update_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: listtransfers
        ##############
        @self._bot.tree.command(name="listtransfers", description="List active BLU migrations")
        @discord.app_commands.describe(identifier="Optional discord name or play key")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _list_transfers_cmd(interaction: discord.Interaction, identifier: str | None = None):
            if identifier:
                if self._is_playkey(identifier):
                    user_id = self._get_user_id_from_key(identifier)
                    if not user_id:
                        await interaction.response.send_message(f'No user found for play key `{identifier}`', ephemeral=True)
                        return
                else:
                    member = discord.utils.get(interaction.guild.members, name=identifier)
                    if not member:
                        await interaction.response.send_message(f'User `{identifier}` not found', ephemeral=True)
                        return
                    user_id = member.id

                state = await asyncio.to_thread(self._get_user_transfer_state, user_id)
                state_name = self._migration_state_to_str(state)
                await interaction.response.send_message(f'`{identifier}`: {state_name}', ephemeral=True)
                return

            transfers = await asyncio.to_thread(self._get_inprogress_transfers)
            queue_snapshot = await asyncio.to_thread(self._get_queued_migrations)
            lines = []
            if transfers:
                for row in transfers:
                    member = discord.utils.get(interaction.guild.members, id=int(row['discord_uuid']))
                    name = member.name if member else row['discord_uuid']
                    if row['migration_state'] != self._migration_state.ERROR_STATE:
                        lines.append(f'**{name}**: `{self._migration_state_to_str(row["migration_state"]) }`')
                    else:
                        lines.append(f'**{name}**: `{self._migration_state_to_str(row["migration_state"]) }` - Error Code: [{row["error_state"]}]')
            else:
                lines.append('No transfers in progress.')

            if queue_snapshot:
                lines.append(f'\n**Queued migrations**: {len(queue_snapshot)}')

            await interaction.response.send_message('\n'.join(lines), ephemeral=True)

        @_list_transfers_cmd.error
        async def _list_transfers_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: disablemigrations
        ##############
        @self._bot.tree.command(name="disablemigrations", description="Disable new BLU migrations")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _disable_migrations_cmd(interaction: discord.Interaction):
            self.migrations_enabled = False
            await self._disable_active_migration_views()
            await interaction.response.send_message('New migrations have been disabled.\n\nA restart of the bot is required for to re-enable', ephemeral=True)
           
           # Log the action to the bot channel
            guild = interaction.guild
            botMessageChannel = discord.utils.get(guild.text_channels, name=BOT_CHANNEL)
            if botMessageChannel:
                await botMessageChannel.send(f'New migrations have been disabled by `{interaction.user}`.')
            else:
                print(f"{self._MODULE_NAME}: New migrations have been disabled by `{interaction.user}`.")

        @_disable_migrations_cmd.error
        async def _disable_migrations_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


        ##############
        # Command: resetmigration
        ##############
        @self._bot.tree.command(name="resetmigration", description="Reset a user\'s migration state")
        @discord.app_commands.describe(identifier="Discord username or play key")
        @discord.app_commands.checks.has_role(COMMAND_ROLE)
        async def _reset_migration_cmd(interaction: discord.Interaction, identifier: str):
            if self._is_playkey(identifier):
                user_id = self._get_user_id_from_key(identifier)
                if not user_id:
                    await interaction.response.send_message(f'No user found for play key `{identifier}`', ephemeral=True)
                    return
            else:
                member = discord.utils.get(interaction.guild.members, name=identifier)
                if not member:
                    await interaction.response.send_message(f'User `{identifier}` not found', ephemeral=True)
                    return
                user_id = member.id
            
            # Reset the migration state in the database by deleting their row in the blu_transfers table
            db_connection = self._get_db_connection()
            if not db_connection:
                await interaction.response.send_message("No mysql connection, unable to reset migration state", ephemeral=True)
                return
            cursor = db_connection.cursor()
            cursor.execute('DELETE FROM blu_transfers WHERE discord_uuid=%s', (str(user_id),))
            db_connection.commit()
            success = cursor.rowcount > 0
            cursor.close()
            db_connection.close()
            
            if success:
                await interaction.response.send_message(f'Migration state reset for `{identifier}`.', ephemeral=True)
            else:
                await interaction.response.send_message('Failed to reset migration state.', ephemeral=True)

        @_reset_migration_cmd.error
        async def _reset_migration_cmd_error(interaction: discord.Interaction, error):
            if isinstance(error, discord.app_commands.MissingRole):
                await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)
