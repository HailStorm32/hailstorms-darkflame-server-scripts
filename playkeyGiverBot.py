# Credit to GPT-4o for a good part of the original code, I have fine-tuned and modified it to work with for my needs

import discord
import string
import random
from discord.ext import commands
import mysql.connector
import json
from mysql.connector import Error
from datetime import datetime
import re
from playkeyBotSettings import *


#------------------------------------------------------------------------------------------
# Helper Functions
#------------------------------------------------------------------------------------------

# Set up database connection
def create_connection():
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


def check_DB_connection():
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


# Ensure the discord_uuid column exists in the play_keys table
def ensure_discord_uuid_column_exists(connection):
    if not check_DB_connection():
        print("No mysql connection, unable to check for discord_uuid column")
        return

    cursor = connection.cursor()
    cursor.execute("SHOW COLUMNS FROM play_keys LIKE 'discord_uuid'")
    result = cursor.fetchone()
    if not result:
        cursor.execute("ALTER TABLE play_keys ADD COLUMN discord_uuid VARCHAR(255) DEFAULT NULL")
        connection.commit()
        print("discord_uuid column added to play_keys table")

# Ensure notes column exists in the play_keys table
def ensure_notes_column_exists(connection):
    if not check_DB_connection():
        print("No mysql connection, unable to check for notes column")
        return

    cursor = connection.cursor()
    cursor.execute("SHOW COLUMNS FROM play_keys LIKE 'notes'")
    result = cursor.fetchone()
    if not result:
        cursor.execute("ALTER TABLE play_keys ADD COLUMN notes TEXT DEFAULT NULL")
        connection.commit()
        print("notes column added to play_keys table")


def lock_account(member_name, uuid, player_left=True):
    #Get the play key for the user and the number of times it has been used
    cursor = connection.cursor()
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
            connection.commit()

            if player_left:
                botMessageChannelMessage = f'The user `{member_name}` has left the server. **Their account has been locked.**\nTheir play key was: `{key}`'

                note_message = f'Account locked on leave. Date: {datetime.now()}'
            else:
                botMessageChannelMessage = f'Account has been locked for user `{member_name}`.'

                note_message = f'Account locked by mythran. Date: {datetime.now()}'
        
        #If the key has not been used, deactivate it
        else:
            cursor.execute('UPDATE play_keys SET active=0 WHERE key_string=%s', (str(key),))
            connection.commit()

            if player_left:
                botMessageChannelMessage = f'The user `{member_name}` has left the server. Play key found, but no account. \n **Key has been deactivated.**\nTheir play key was: `{key}`'

                note_message = f'Playkey deactivated on leave. Date: {datetime.now()}'
            else:
                botMessageChannelMessage = f'Playkey for user `{member_name}` has been deactivated. No account found.'

                note_message = f'Playkey deactivated by mythran. Date: {datetime.now()}'
        
        #Save a note for the user that their account/key was locked
        save_note(str(uuid), note_message)

    #If the user does not have a play key
    else:
        if player_left:
            botMessageChannelMessage = f'The user `{member_name}` has left the server. **No play key found for them.**'
        else:
            botMessageChannelMessage = f'The user `{member_name}` does not have a playkey'

    return botMessageChannelMessage 


def unlock_account(member_name, uuid):
    # Get the play key for the user
    cursor = connection.cursor()
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
            connection.commit()

            botMessageChannelMessage = f'Account unlocked for user `{member_name}`.'

            note_message = f'Account unlocked by mythran. Date: {datetime.now()}'

        # Reactivate the play key if it was deactivated
        else:
            cursor.execute('UPDATE play_keys SET active=1 WHERE key_string=%s', (str(key),))
            connection.commit()

            botMessageChannelMessage = f'Playkey for user `{member_name}` has been reactivated. No account found.'

            note_message = f'Playkey reactivated by mythran. Date: {datetime.now()}'
        
        # Save a note for the user that their account/key was unlocked/reactivated
        save_note(str(uuid), note_message)

    # If the user does not have a play key
    else:
        botMessageChannelMessage = f'The user `{member_name}` does not have a playkey'

    return botMessageChannelMessage


def generate_new_key():
    key = ""
    for j in range(4):
        key += ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(4)) + '-'

    # Remove last dash
    key = key[:-1]

    return key


def save_note(uuid_str, note, is_key=False):
    cursor = connection.cursor()
    cursor.execute('SELECT notes FROM play_keys WHERE discord_uuid=%s', (uuid_str,))
    result = cursor.fetchone()

    if result:
        notes = json.loads(result[0]) if result[0] else []
        note_id = len(notes)
        if is_key:
            notes.append({"id": note_id, "key": note})
        else:
            notes.append({"id": note_id, "note": note})
        cursor.execute('UPDATE play_keys SET notes=%s WHERE discord_uuid=%s', (json.dumps(notes), uuid_str))
        connection.commit()
        return note_id
    else:
        return -1


def is_playkey(identifier):
    pattern = re.compile(r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$')
    return bool(pattern.match(identifier))

def get_key_from_user_id(user_id):
    cursor = connection.cursor()
    cursor.execute('SELECT key_string FROM play_keys WHERE discord_uuid=%s', (str(user_id),))
    result = cursor.fetchone()
    return result[0] if result else None

def get_user_id_from_key(key):
    cursor = connection.cursor()
    cursor.execute('SELECT discord_uuid FROM play_keys WHERE key_string=%s', (key,))
    result = cursor.fetchone()
    return result[0] if result else None

#------------------------------------------------------------------------------------------
# Main
#------------------------------------------------------------------------------------------

if __name__ == "__main__":
    connection = create_connection()

    ensure_discord_uuid_column_exists(connection)
    ensure_notes_column_exists(connection)

    # Set up the bot
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.members = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    #------------------------------------------------------------------------------------------
    # Event Handlers
    #------------------------------------------------------------------------------------------
    @bot.event
    async def on_ready():
        print(f'We have logged in as {bot.user}')
        try:
            synced = await bot.tree.sync()
            print(f'Successfully synced {len(synced)} commands')
        except Exception as e:
            print(f'Failed to sync commands: {e}')

    @bot.event
    async def on_message(message):
        if isinstance(message.channel, discord.TextChannel) and message.channel.name == REQUEST_CHANNEL and not message.author.bot:
            await message.add_reaction('✅')

            if not check_DB_connection():
                print("No mysql connection, unable to generate play key")
                await message.add_reaction('⚠️')
                return
            
            key = get_key_from_user_id(message.author.id)

            if key:
                await message.add_reaction('❌')
                try:
                    await message.author.send(f'You already have an account with Nexus Universe. Your play key is: `{key}`\n\nIf you need to reset your password, please do so here: https://dashboard.nexusuniverse.online/user/forgot-password \n\nIf you recently left the Discord, you can unlock your account/key by DMing a Mythran')
                except discord.Forbidden:
                    await message.add_reaction('‼️')
                    role = discord.utils.get(message.guild.roles, name=ROLE_TO_PING)
                    thread = await message.create_thread(name="DM Disabled", auto_archive_duration=1440)  # Auto-archive after 24 hours
                    await thread.send(f'{role.mention}, the user {message.author.mention} already has a key, but DMs are disabled and needs assistance.')
            else:
                uuid_str = str(message.author.id)
                cursor = connection.cursor()
                new_key = generate_new_key() # Generate a new key
                cursor.execute('INSERT INTO play_keys (key_string, key_uses, active, discord_uuid) VALUES (%s, %s, %s, %s)',
                            (new_key, 1, 1, uuid_str))
                connection.commit()

                try:
                    await message.author.send(f'Your Nexus Universe play key is: `{new_key}`\n\nIf you leave the Discord, your account/key will be locked. ')
                    await message.add_reaction('👍')
                except discord.Forbidden:
                    await message.add_reaction('‼️')
                    role = discord.utils.get(message.guild.roles, name=ROLE_TO_PING)
                    thread = await message.create_thread(name="DM Disabled", auto_archive_duration=1440)  # Auto-archive after 24 hours
                    await thread.send(f'{role.mention}, the user {message.author.mention} has DMs disabled and needs assistance. A key has already been generated for them and can be found using commands')

    @bot.event
    async def on_member_remove(member):
        if LOCK_ON_LEAVE:
            guild = member.guild
            botMessageChannel = discord.utils.get(guild.text_channels, name=BOT_CHANNEL) 

            if not check_DB_connection():
                if botMessageChannel:
                    await botMessageChannel.send(f'⚠️ Unable to lock account of user `{member.name}`. No connection to DB!`')
                return

            if botMessageChannel:
                botMessageChannelMessage = lock_account(member.name, member.id)
                await botMessageChannel.send(botMessageChannelMessage)


    #------------------------------------------------------------------------------------------
    # Commands
    #------------------------------------------------------------------------------------------

    ##############
    # Command: lockaccount
    ##############
    @bot.tree.command(name="lockaccount", description="Lock the account of a user")
    @discord.app_commands.describe(identifier="The username or key of the user")
    @discord.app_commands.checks.has_role(COMMAND_ROLE)
    async def lock_account_cmd(interaction: discord.Interaction, identifier: str):
        if not check_DB_connection():
            await interaction.response.send_message("No mysql connection, unable to add note", ephemeral=True)
            return

        # Check if the identifier is a play key
        if is_playkey(identifier):
            uuid = get_user_id_from_key(identifier)
            
            if uuid:
                user = discord.utils.get(interaction.guild.members, id=int(uuid))
            else:
                await interaction.response.send_message(f'User with name/play-key `{identifier}` not found', ephemeral=True)
                return
        else:
            user = discord.utils.get(interaction.guild.members, name=identifier)
        
        if user:
            message = lock_account(user.name, user.id, False)
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.response.send_message(f'User with name/play-key `{identifier}` not found', ephemeral=True)

    @lock_account_cmd.error
    async def lock_account_cmd_error(interaction: discord.Interaction, error):
        if isinstance(error, discord.app_commands.MissingRole):
            await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


    ##############
    # Command: unlockaccount
    ##############
    @bot.tree.command(name="unlockaccount", description="Unlock the account of a user")
    @discord.app_commands.describe(identifier="The username or key of the user")
    @discord.app_commands.checks.has_role(COMMAND_ROLE)
    async def unlock_account_cmd(interaction: discord.Interaction, identifier: str):
        if not check_DB_connection():
            await interaction.response.send_message("No mysql connection, unable to add note", ephemeral=True)
            return

        # Check if the identifier is a play key
        if is_playkey(identifier):
            uuid = get_user_id_from_key(identifier)
            
            if uuid:
                user = discord.utils.get(interaction.guild.members, id=int(uuid))
            else:
                await interaction.response.send_message(f'User with name/play-key `{identifier}` not found', ephemeral=True)
                return
        else:
            user = discord.utils.get(interaction.guild.members, name=identifier)

        if user:
            message = unlock_account(user.name, user.id)
            await interaction.response.send_message(message, ephemeral=True)          
        else:
            await interaction.response.send_message(f'User with name/play-key `{identifier}` not found', ephemeral=True)

    @unlock_account_cmd.error
    async def unlock_account_cmd_error(interaction: discord.Interaction, error):
        if isinstance(error, discord.app_commands.MissingRole):
            await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


    ##############
    # Command: addnote
    ##############
    @bot.tree.command(name="addnote", description="Add a note to a user")
    @discord.app_commands.describe(username="The username of the user", note="The note to add")
    @discord.app_commands.checks.has_role(COMMAND_ROLE)
    async def add_note_cmd(interaction: discord.Interaction, username: str, note: str):
        if not check_DB_connection():
            await interaction.response.send_message("No mysql connection, unable to add note", ephemeral=True)
            return

        user = discord.utils.get(interaction.guild.members, name=username)
        if user:
            note_id = save_note(str(user.id), note)
            if note_id >= 0:
                await interaction.response.send_message(f'Note added for {username}: [{note_id}] {note}', ephemeral=True)
            else:
                await interaction.response.send_message(f'No play key found for user {username}', ephemeral=True)
        else:
            await interaction.response.send_message(f'User {username} not found', ephemeral=True)

    @add_note_cmd.error
    async def add_note_cmd_error(interaction: discord.Interaction, error):
        if isinstance(error, discord.app_commands.MissingRole):
            await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


    ##############
    # Command: displaynotes
    ##############
    @bot.tree.command(name="displaynotes", description="Display notes for a user")
    @discord.app_commands.describe(username="The username of the user")
    @discord.app_commands.checks.has_role(COMMAND_ROLE)
    async def display_notes_cmd(interaction: discord.Interaction, username: str):
        if not check_DB_connection():
            await interaction.response.send_message("No mysql connection, unable to display notes", ephemeral=True)
            return

        user = discord.utils.get(interaction.guild.members, name=username)
        if user:
            uuid_str = str(user.id)
            cursor = connection.cursor()
            cursor.execute('SELECT notes FROM play_keys WHERE discord_uuid=%s', (uuid_str,))
            result = cursor.fetchone()

            if result:
                notes = json.loads(result[0]) if result[0] else []
                notes_display = "\n".join([f'[{note["id"]}] {note["note"]}' for note in notes]) if notes else "No notes found."
                await interaction.response.send_message(f'Notes for {username}:\n{notes_display}', ephemeral=True)
            else:
                await interaction.response.send_message(f'No play key found for user {username}', ephemeral=True)
        else:
            await interaction.response.send_message(f'User {username} not found', ephemeral=True)

    @display_notes_cmd.error
    async def display_notes_cmd_error(interaction: discord.Interaction, error):
        if isinstance(error, discord.app_commands.MissingRole):
            await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


    ##############
    # Command: showkey
    ##############
    @bot.tree.command(name="showkey", description="Show play key for a user")
    @discord.app_commands.describe(username="The username of the user")
    @discord.app_commands.checks.has_role(COMMAND_ROLE)
    async def show_key_cmd(interaction: discord.Interaction, username: str):
        if not check_DB_connection():
            await interaction.response.send_message("No mysql connection, unable to display play key", ephemeral=True)
            return

        user = discord.utils.get(interaction.guild.members, name=username)
        if user:
            key = get_key_from_user_id(user.id)

            if key:
                await interaction.response.send_message(f'Play key for {username}: {key}', ephemeral=True)
            else:
                await interaction.response.send_message(f'No play key found for user {username}', ephemeral=True)
        else:
            await interaction.response.send_message(f'User {username} not found', ephemeral=True)

    @show_key_cmd.error
    async def show_key_cmd_error(interaction: discord.Interaction, error):
        if isinstance(error, discord.app_commands.MissingRole):
            await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)
    

    ##############
    # Command: showaccount
    ##############
    @bot.tree.command(name="showaccount", description="Show Discord account name tied to a play key")
    @discord.app_commands.describe(key="The play key to look up")
    @discord.app_commands.checks.has_role(COMMAND_ROLE)
    async def show_account_cmd(interaction: discord.Interaction, key: str):
        if not check_DB_connection():
            await interaction.response.send_message("No mysql connection, unable to display account", ephemeral=True)
            return

        uuid = get_user_id_from_key(key)

        if uuid:
            user = discord.utils.get(interaction.guild.members, id=int(uuid))
            if user:
                await interaction.response.send_message(f'Account name for play key `{key}`: `{user.name}`', ephemeral=True)
            else:
                await interaction.response.send_message(f'No account found for uuid: `{uuid}`', ephemeral=True)
        else:
            await interaction.response.send_message(f'No account found for play key: `{key}`', ephemeral=True)
    
    @show_account_cmd.error
    async def show_account_cmd_error(interaction: discord.Interaction, error):
        if isinstance(error, discord.app_commands.MissingRole):
            await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


    ##############
    # Command: removenote
    ##############
    @bot.tree.command(name="removenote", description="Remove a note from a user by ID")
    @discord.app_commands.describe(username="The username of the user", note_id="The ID of the note to remove")
    @discord.app_commands.checks.has_role(COMMAND_ROLE)
    async def remove_note_cmd(interaction: discord.Interaction, username: str, note_id: int):
        if not check_DB_connection():
            await interaction.response.send_message("No mysql connection, unable to remove note", ephemeral=True)
            return

        user = discord.utils.get(interaction.guild.members, name=username)
        if user:
            uuid_str = str(user.id)
            cursor = connection.cursor()
            cursor.execute('SELECT notes FROM play_keys WHERE discord_uuid=%s', (uuid_str,))
            result = cursor.fetchone()

            if result:
                notes = json.loads(result[0]) if result[0] else []
                if note_id < 0 or note_id >= len(notes):
                    await interaction.response.send_message(f'Note with ID {note_id} does not exist for {username}', ephemeral=True)
                    return
                notes = [note for i, note in enumerate(notes) if i != note_id]
                for i, note in enumerate(notes):
                    note["id"] = i
                cursor.execute('UPDATE play_keys SET notes=%s WHERE discord_uuid=%s', (json.dumps(notes), uuid_str))
                connection.commit()
                await interaction.response.send_message(f'Note with ID {note_id} removed for {username}', ephemeral=True)
            else:
                await interaction.response.send_message(f'No play key found for user {username}', ephemeral=True)
        else:
            await interaction.response.send_message(f'User {username} not found', ephemeral=True)

    @remove_note_cmd.error
    async def remove_note_cmd_error(interaction: discord.Interaction, error):
        if isinstance(error, discord.app_commands.MissingRole):
            await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)


    # Run the bot
    bot.run(DISCORD_TOKEN)
