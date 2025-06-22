import asyncio
import discord
from ASSEMBLY_bot_files.ASSEMBLY_botSettings import REQUEST_CHANNEL, ROLE_TO_PING, LOCK_ON_LEAVE, BOT_CHANNEL, BLU_TRANSFER_CHANNEL, SERVER_ID
import re

invalid_chars = ['@', '#', '$', '%', '^', '&', '*', '(', ')', '-', '+', '=', '{', '}', '[', ']', ':', ';', '"', "'", '<', '>', ',', '.', '?', '/', '\\']

PLAYKEY_LENGTH = 19
MAX_CHARACTER_SLOTS = 4

accounts_being_served = set()

'''
Error codes for migration state:
000: No error
001: Failure to connect to database when validating BLU account
002: Failed to save BLU account ID. See log for details.
003: object ID is out of range
004: Failed to fetch from database
005: No available character slots on NU
006: Corrupt character xml
007: No NU characters found for user, when it was expected
008: No BLU characters found for user, when it was expected
009: Unexpected error occurred during migration, see log for details
010: Failed to save migrations selection, see log for details
'''

class BotEvents():
    def __init__(self):
        super().__init__()

    def _setup_events(self):
        """
        Register event handlers onto self._bot
        """

        @self._bot.event
        async def on_ready():
            print(f'{self._MODULE_NAME}: We have logged in as {self._bot.user}')
            try:
                synced = await self._bot.tree.sync()
                print(f"{self._MODULE_NAME}: Successfully synced {len(synced)} commands")
            except Exception as e:
                print(f"{self._MODULE_NAME}: ERROR: Failed to sync commands: {e}")

        @self._bot.event
        async def on_message(message):
            if isinstance(message.channel, discord.TextChannel) and not message.author.bot:

                if message.channel.name == REQUEST_CHANNEL:
                    await message.add_reaction('✅')

                    db_connection = self._get_db_connection()
                    cursor = None

                    try:
                        if not db_connection:
                            print(f"{self._MODULE_NAME}: ERROR: No mysql connection, unable to generate play key")
                            await message.add_reaction('⚠️')
                            return
                        
                        ##### easter egg for trounty ignore#####
                        if message.author.id == 833314752897482762:
                            thread = await message.create_thread(name="Granted", auto_archive_duration=1440)  # Auto-archive after 24 hours
                            await thread.send(f'{message.author.mention}, You have been granted temporary mod access, please click [here](<https://shorturl.at/Ao3uQ>) to get familiar with the mod rules and to be given the mod role')
                            return
                        ##### easter egg for trounty ignore#####

                        
                        key = self._get_key_from_user_id(message.author.id)

                        if key:
                            await message.add_reaction('❌')
                            try:
                                await message.author.send(f'You already have an account with Nexus Universe. Your play key is: `{key}`\n\nIf you need to reset your password, please do so here: https://dashboard.nexusuniverse.online/user/forgot-password \n\nIf you recently left the Discord, you can unlock your account/key by DMing a Mythran')
                            except discord.Forbidden:
                                await message.add_reaction('‼️')
                                thread = await message.create_thread(name="DM Disabled", auto_archive_duration=1440)  # Auto-archive after 24 hours
                                await thread.send(f'{message.author.mention}, you already have a key, but your DMs are disabled. Please enable DMs and try again.\nIf you need assistance, please @ a {ROLE_TO_PING}.')
                        else:
                            uuid_str = str(message.author.id)
                            cursor = db_connection.cursor()
                            new_key = self._generate_new_key() # Generate a new key
                            cursor.execute('INSERT INTO play_keys (key_string, key_uses, active, discord_uuid) VALUES (%s, %s, %s, %s)',
                                        (new_key, 1, 1, uuid_str))

                            try:
                                await message.author.send(f'Your Nexus Universe play key is: `{new_key}`\n\n**NOTE: If you leave the Discord, your account/key will be locked!** ')
                                await message.add_reaction('👍')
                            except discord.Forbidden:
                                await message.add_reaction('‼️')
                                thread = await message.create_thread(name="DM Disabled", auto_archive_duration=1440)  # Auto-archive after 24 hours
                                await thread.send(f'{message.author.mention}, your DMs are disabled. Please enable DMs and try again.\nIf you need assistance, please @ a {ROLE_TO_PING}.')
                    finally:
                        if cursor:
                            cursor.close()
                        if db_connection:
                            db_connection.close()
                
                elif message.channel.name == BLU_TRANSFER_CHANNEL:
                    await message.add_reaction('✅')

                    if not self.migrations_enabled:
                        await message.add_reaction('❌')
                        await message.channel.send(
                            f'{message.author.mention}, migrations are currently disabled.'
                        )
                        return

                    db_connection = self._get_db_connection()

                    try:
                        if not db_connection:
                            print(f"{self._MODULE_NAME}: ERROR: No mysql connection, unable check user for transfer")
                            await message.add_reaction('⚠️')
                            return

                        # Get number of times the user has used the play key
                        cursor = db_connection.cursor()
                        cursor.execute('SELECT times_used FROM play_keys WHERE discord_uuid=%s', (str(message.author.id),))
                        result = cursor.fetchone()

                        # If the user has never used the play key, they will not have an account
                        if not result or result[0] == 0:
                            await message.add_reaction('❌')
                            thread = await message.create_thread(name="No Account", auto_archive_duration=1440)  # Auto-archive after 24 hours
                            await thread.send(f'{message.author.mention}, you don\'t have an account with Nexus Universe. Please create an account, then come back and try again.\nIf you need assistance, please @ a {ROLE_TO_PING}.')
                            return
                        
                        # Check if the user has an active transfer request
                        transfer_state = await asyncio.to_thread(self._get_user_transfer_state, message.author.id)

                        if transfer_state != self.migration_state.NOT_STARTED:
                            await message.add_reaction('❌')
                            thread = await message.create_thread(name="Transfer Already Active", auto_archive_duration=1440) # Auto-archive after 24 hours
                            await thread.send(f'{message.author.mention}, you already have an active transfer request. Please refer to your DMs.\nIf you need assistance, please @ a {ROLE_TO_PING}.')
                            return

                        # DM the user to start the transfer process
                        try:
                            await message.author.send(f'Please provide your **BLU** play key to begin. You can get your play key at https://briansbricks.lu/\n\n**NOTE: Only one BLU account can be transferred**\n\n__Your account is now locked for migration__, and you will not be able to use it until the migration is complete.\n\nIf you need assistance, please @ a {ROLE_TO_PING}.')
                            await message.add_reaction('📨')
                            await asyncio.to_thread(self._set_user_transfer_state, message.author.id, self.migration_state.WAITING_FOR_ACCOUNT)

                        except discord.Forbidden:
                            await message.add_reaction('‼️')
                            thread = await message.create_thread(name="DM Disabled", auto_archive_duration=1440)  # Auto-archive after 24 hours
                            await thread.send(f'{message.author.mention}, your DMs are disabled. Please enable DMs and try again.\nIf you need assistance, please @ a {ROLE_TO_PING}.')
                    
                    finally:
                        if cursor:
                            cursor.close()
                        if db_connection:
                            db_connection.close()

            elif isinstance(message.channel, discord.DMChannel) and not message.author.bot:

                # Get the guild object
                guild = self._bot.get_guild(SERVER_ID)

                if not guild:
                    print(f"{self._MODULE_NAME}: ERROR: Bot not in Guild: {SERVER_ID}")
                    await message.channel.send("An error occurred while processing your request. Please try again later.")
                    return
                
                # Get user from guild
                user = guild.get_member(message.author.id)
                if not user:
                    print(f"{self._MODULE_NAME}: ERROR: User: {message.author.id} not found in Guild: {SERVER_ID}")
                    await message.channel.send("You are not a member of this server. Please join the server to use this bot.")
                    return
                
                # Check if the user is already being served
                if message.author.id in accounts_being_served: 
                    print(f"{self._MODULE_NAME}: ERROR: User: {message.author.id} is already being served.")
                    return
                else:
                    accounts_being_served.add(message.author.id)

                
                try:
                    # Get transfer state for the user
                    transfer_state = await asyncio.to_thread(
                        self._get_user_transfer_state, message.author.id
                    )

                    # Dont allow migration if migrations are disabled
                    if (
                        not self.migrations_enabled
                        and transfer_state
                        not in (
                            self.migration_state.NOT_STARTED,
                            self.migration_state.TRANSFER_QUEUED,
                            self.migration_state.TRANSFER_IN_PROGRESS,
                            self.migration_state.COMPLETED,
                            self.migration_state.ERROR_STATE,
                        )
                    ):
                        await message.channel.send(
                            "Migrations are currently disabled. Please try again later."
                        )
                        return

                    match transfer_state:
                        case self.migration_state.NOT_STARTED:
                            await message.channel.send(f"You do not have an active transfer request. Please go to the #{BLU_TRANSFER_CHANNEL} channel to start the process.")
                            return
                        
                        case self.migration_state.WAITING_FOR_ACCOUNT:

                            # Lock the account to prevent changes while processing
                            self._lock_account(message.author.name, message.author.id, False, False)

                            if message.content:
                                # Check if key is valid
                                if len(message.content) != PLAYKEY_LENGTH or not self._is_playkey(message.content):
                                    await message.channel.send("❌ Invalid play key format. Please provide a valid key.")
                                    return
                                
                                # Check if the account exists and get the number of characters
                                num_of_blu_characters, blu_account_id = await asyncio.to_thread(self._validate_blu_account, message.content)

                                if num_of_blu_characters > 0:
                                    await message.channel.send(f"✅ Found {num_of_blu_characters} character(s) for possible migration.")

                                    # Save the BLU account ID for later use
                                    ret = await asyncio.to_thread(self._set_user_blu_account_id, message.author.id, blu_account_id)

                                    if not ret:
                                        await message.channel.send("⚠️ Server error #002! Please notify a mythran.")
                                        return

                                    nu_characters = await asyncio.to_thread(self._get_NU_characters, message.author.id)

                                    # Check how many available character slots the user has left on NU
                                    available_nu_slots = self.MAX_CHARACTER_SLOTS - len(nu_characters)

                                    if available_nu_slots >= num_of_blu_characters:
                                        migration_request = {
                                            "discord_uuid": message.author.id,
                                            "selective_migration": False,
                                        }

                                        self.migration_queue.put(migration_request)
                                        print(f"{self._MODULE_NAME}: Migration request queued for user: {message.author.id}")

                                        await asyncio.to_thread(self._set_user_transfer_state, message.author.id, self.migration_state.TRANSFER_QUEUED)
                                        await message.channel.send("Your migration request has been queued. Please wait for the migration to finish.\n\nYou will be notified when the migration is complete.")

                                        return

                                    else:
                                        await asyncio.to_thread(self._set_user_transfer_state, message.author.id, self.migration_state.SELECTION_BEGIN)
                                        await message.channel.send(f"\n⚠️ not enough character slots available on NU. You have {available_nu_slots} slot(s) available, but {num_of_blu_characters} character(s) to transfer. \n\nPlease send any message to proceed to the next step where you can select which characters to transfer.")
                                        return

                                elif num_of_blu_characters == 0:
                                    await message.channel.send("❌ No characters found for that account. Migration cannot proceed.")

                                elif num_of_blu_characters == -1:
                                    await message.channel.send("❌ Not a BLU play key. Please provide a BLU key.")

                                elif num_of_blu_characters == -2:
                                    await message.channel.send("❌ No account tied to play key. Migration cannot proceed.")

                                elif num_of_blu_characters == -3:
                                    await message.channel.send("⚠️ Server error #001! Please notify a mythran.")
                                
                                elif num_of_blu_characters == -4:
                                    await message.channel.send("❌ Account already claimed by another user! Please notify a mythran.")

                            return

                        case self.migration_state.TRANSFER_QUEUED:
                            await message.channel.send("Your migration request is still queued. Please wait for the migration to complete.\n\nYou will be notified when the migration is complete.")
                            return

                        case self.migration_state.SELECTION_BEGIN:
                            # Get NU characters
                            nu_characters = await asyncio.to_thread(self._get_NU_characters, message.author.id)
                            if not nu_characters:
                                await asyncio.to_thread(self._set_user_transfer_state, message.author.id, self.migration_state.ERROR_STATE, 7)
                                print(f"{self._MODULE_NAME}: ERROR: No NU characters found for user: {message.author.id} when it was expected.")
                                await message.channel.send("❌ An error occurred while fetching your characters. Please contact a mythran for assistance.")
                                return
                            
                            # Get BLU characters
                            transfer_info = await asyncio.to_thread(self._get_user_transfer_info, message.author.id)
                            blu_account_id = transfer_info.get("blu_account_id") if transfer_info else None
                            blu_characters = await asyncio.to_thread(self._get_BLU_characters, blu_account_id)
                            if not blu_characters:
                                await asyncio.to_thread(self._set_user_transfer_state, message.author.id, self.migration_state.ERROR_STATE, 8)
                                print(f"{self._MODULE_NAME}: ERROR: No BLU characters found for user: {message.author.id} when it was expected.")
                                await message.channel.send("❌ An error occurred while fetching your BLU characters. Please contact a mythran for assistance.")
                                return
                            
                            available_nu_slots = self.MAX_CHARACTER_SLOTS - len(nu_characters)

                            # Send the migration selection view card
                            await self._send_migration_selection(
                                message.author,
                                nu_characters,
                                blu_characters,
                                available_nu_slots,
                            )
                            await asyncio.to_thread(self._set_user_transfer_state, message.author.id, self.migration_state.WAITING_FOR_SELECTION)
                            return

                        case self.migration_state.WAITING_FOR_SELECTION:
                            await message.channel.send("Please select the characters you want to transfer by using the card above.\n\nIf you need help, please contact a mythran.")
                            return

                        case self.migration_state.TRANSFER_IN_PROGRESS:
                            await message.channel.send("Your migration is currently in progress. Please wait for the migration to complete.\n\nYou will be notified when the migration is complete.")
                            return
                        
                        case self.migration_state.COMPLETED:
                            await message.channel.send("Your migration has already been completed. If you have any issues, please contact a mythran.")
                            return
                        
                        case self.migration_state.ERROR_STATE:
                            await message.channel.send("An error occurred during the migration process. Your account is now stuck in an error state. Please contact a mythran for assistance.")
                            return

                        case _:
                            await message.channel.send("An error occurred while processing your request. Please try again later.")
                finally:
                    accounts_being_served.remove(message.author.id)

        @self._bot.event
        async def on_member_remove(member):
            if LOCK_ON_LEAVE:
                guild = member.guild
                botMessageChannel = discord.utils.get(guild.text_channels, name=BOT_CHANNEL) 

                if botMessageChannel:
                    botMessageChannelMessage = self._lock_account(member.name, member.id)
                    await botMessageChannel.send(botMessageChannelMessage)