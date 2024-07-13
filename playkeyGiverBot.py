# Credit to GPT-4o for the original code, I have fine-tuned it to work with for my needs

import discord
import string
import random
from discord.ext import commands
import mysql.connector
import json
from mysql.connector import Error
from datetime import datetime
from playkeyBotSettings import *

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

connection = create_connection()

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

ensure_discord_uuid_column_exists(connection)

# Set up the bot
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

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

        uuid_str = str(message.author.id)
        cursor = connection.cursor()
        cursor.execute('SELECT key_string FROM play_keys WHERE discord_uuid=%s', (uuid_str,))
        result = cursor.fetchone()

        if result:
            await message.add_reaction('❌')
            try:
                await message.author.send(f'You already have an account with Nexus Universe. Your play key is: `{result[0]}`\n\nIf you need to reset your password, please do so here: https://dashboard.legouniverse.best/user/forgot-password')
            except discord.Forbidden:
                await message.add_reaction('‼️')
                role = discord.utils.get(message.guild.roles, name=ROLE_TO_PING)
                thread = await message.create_thread(name="DM Disabled", auto_archive_duration=1440)  # Auto-archive after 24 hours
                await thread.send(f'{role.mention}, the user {message.author.mention} already has a key, but DMs are disabled and needs assistance.')
        else:
            new_key = generate_new_key()  # Placeholder for key generation logic
            cursor.execute('INSERT INTO play_keys (key_string, key_uses, active, discord_uuid) VALUES (%s, %s, %s, %s)',
                           (new_key, 1, 1, uuid_str))
            connection.commit()

            try:
                await message.author.send(f'Your Nexus Universe play key is: `{new_key}`')
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
                await botMessageChannel.send(f'⚠️ Unable to lock account of user `{member.name}`. No connection to DB! \nTheir play key was: `{key}`')
            return

        #Get the play key for the user and the number of times it has been used
        cursor = connection.cursor()
        cursor.execute('SELECT key_string,times_used,id FROM play_keys WHERE discord_uuid=%s', (str(member.id),))
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

                if botMessageChannel:
                    await botMessageChannel.send(f'The user `{member.name}` has left the server. **Their account has been locked.**\nTheir play key was: `{key}`')

                note_message = f'Account locked on leave. Date: {datetime.now()}'
            
            #If the key has not been used, deactivate it
            else:
                cursor.execute('UPDATE play_keys SET active=0 WHERE key_string=%s', (str(key),))
                connection.commit()

                if botMessageChannel:
                    await botMessageChannel.send(f'The user `{member.name}` has left the server. Play key found, but no account. \n **Key has been deactivated.**\nTheir play key was: `{key}`')

                note_message = f'Playkey deactivated on leave. Date: {datetime.now()}'
            
            #Save a note for the user that their account/key was locked
            save_note(str(member.id), note_message)

        #If the user does not have a play key
        else:
            if botMessageChannel:
                await botMessageChannel.send(f'The user `{member.name}` has left the server. No play key found for them.')


def generate_new_key():
    key = ""
    for j in range(4):
        key += ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(4)) + '-'

    # Remove last dash
    key = key[:-1]

    return key

def save_note(uuid_str, note):
    cursor = connection.cursor()
    cursor.execute('SELECT notes FROM play_keys WHERE discord_uuid=%s', (uuid_str,))
    result = cursor.fetchone()

    if result:
        notes = json.loads(result[0]) if result[0] else []
        note_id = len(notes)
        notes.append({"id": note_id, "note": note})
        cursor.execute('UPDATE play_keys SET notes=%s WHERE discord_uuid=%s', (json.dumps(notes), uuid_str))
        connection.commit()
        return True
    else:
        return False

@bot.tree.command(name="addnote", description="Add a note to a user")
@discord.app_commands.describe(username="The username of the user", note="The note to add")
@discord.app_commands.checks.has_role(COMMAND_ROLE)
async def add_note(interaction: discord.Interaction, username: str, note: str):
    if not check_DB_connection():
        await interaction.response.send_message("No mysql connection, unable to add note", ephemeral=True)
        return

    user = discord.utils.get(interaction.guild.members, name=username)
    if user:
        if save_note(str(user.id), note):
            await interaction.response.send_message(f'Note added for {username}: [{note_id}] {note}', ephemeral=True)
        else:
            await interaction.response.send_message(f'No play key found for user {username}', ephemeral=True)
    else:
        await interaction.response.send_message(f'User {username} not found', ephemeral=True)

@add_note.error
async def add_note_error(interaction: discord.Interaction, error):
    if isinstance(error, discord.app_commands.MissingRole):
        await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)

@bot.tree.command(name="displaynotes", description="Display notes for a user")
@discord.app_commands.describe(username="The username of the user")
@discord.app_commands.checks.has_role(COMMAND_ROLE)
async def display_notes(interaction: discord.Interaction, username: str):
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

@display_notes.error
async def display_notes_error(interaction: discord.Interaction, error):
    if isinstance(error, discord.app_commands.MissingRole):
        await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)

@bot.tree.command(name="showkey", description="Show play key for a user")
@discord.app_commands.describe(username="The username of the user")
@discord.app_commands.checks.has_role(COMMAND_ROLE)
async def show_key(interaction: discord.Interaction, username: str):
    if not check_DB_connection():
        await interaction.response.send_message("No mysql connection, unable to display play key", ephemeral=True)
        return

    user = discord.utils.get(interaction.guild.members, name=username)
    if user:
        uuid_str = str(user.id)
        cursor = connection.cursor()
        cursor.execute('SELECT key_string FROM play_keys WHERE discord_uuid=%s', (uuid_str,))
        result = cursor.fetchone()

        if result:
            await interaction.response.send_message(f'Play key for {username}: {result[0]}', ephemeral=True)
        else:
            await interaction.response.send_message(f'No play key found for user {username}', ephemeral=True)
    else:
        await interaction.response.send_message(f'User {username} not found', ephemeral=True)

@show_key.error
async def show_key_error(interaction: discord.Interaction, error):
    if isinstance(error, discord.app_commands.MissingRole):
        await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)

@bot.tree.command(name="removenote", description="Remove a note from a user by ID")
@discord.app_commands.describe(username="The username of the user", note_id="The ID of the note to remove")
@discord.app_commands.checks.has_role(COMMAND_ROLE)
async def remove_note(interaction: discord.Interaction, username: str, note_id: int):
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

@remove_note.error
async def remove_note_error(interaction: discord.Interaction, error):
    if isinstance(error, discord.app_commands.MissingRole):
        await interaction.response.send_message("You do not have the required role to use this command.", ephemeral=True)

# Run the bot
bot.run(DISCORD_TOKEN)

