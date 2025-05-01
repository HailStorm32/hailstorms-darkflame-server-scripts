import asyncio
import discord
from ASSEMBLY_bot_files.ASSEMBLY_botSettings import REQUEST_CHANNEL, ROLE_TO_PING, LOCK_ON_LEAVE, BOT_CHANNEL, BLU_TRANSFER_CHANNEL, SERVER_ID

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
                        db_connection.commit()
                        cursor.close()

                        try:
                            await message.author.send(f'Your Nexus Universe play key is: `{new_key}`\n\n**NOTE: If you leave the Discord, your account/key will be locked!** ')
                            await message.add_reaction('👍')
                        except discord.Forbidden:
                            await message.add_reaction('‼️')
                            thread = await message.create_thread(name="DM Disabled", auto_archive_duration=1440)  # Auto-archive after 24 hours
                            await thread.send(f'{message.author.mention}, your DMs are disabled. Please enable DMs and try again.\nIf you need assistance, please @ a {ROLE_TO_PING}.')
                
                elif message.channel.name == BLU_TRANSFER_CHANNEL:
                    await message.add_reaction('✅')

                    db_connection = self._get_db_connection()

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
                        cursor.close()
                        db_connection.close()
                        return
                    
                    # Check if the user has an active transfer request
                    transfer_state = await asyncio.to_thread(self._get_user_transfer_state, message.author.id)

                    if transfer_state != self.migration_state.NOT_STARTED:
                        await message.add_reaction('❌')
                        thread = await message.create_thread(name="Transfer Already Active", auto_archive_duration=1440) # Auto-archive after 24 hours
                        await thread.send(f'{message.author.mention}, you already have an active transfer request. Please refer to your DMs.\nIf you need assistance, please @ a {ROLE_TO_PING}.')
                        cursor.close()
                        db_connection.close()
                        return

                    # DM the user to start the transfer process
                    try:
                        await message.author.send(f'Please provide your BLU account username to begin. \n\n**NOTE: Only one BLU account can be transferred** ')
                        await message.add_reaction('📨')
                        await asyncio.to_thread(self._set_user_transfer_state, message.author.id, self.migration_state.WAITING_FOR_ACCOUNT)

                    except discord.Forbidden:
                        await message.add_reaction('‼️')
                        thread = await message.create_thread(name="DM Disabled", auto_archive_duration=1440)  # Auto-archive after 24 hours
                        await thread.send(f'{message.author.mention}, your DMs are disabled. Please enable DMs and try again.\nIf you need assistance, please @ a {ROLE_TO_PING}.')
                    
                
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
                
                # Get transfer state for the user
                transfer_state = await asyncio.to_thread(self._get_user_transfer_state, message.author.id)

                match transfer_state:
                    case "active":
                        await message.channel.send("You already have an active transfer request. Please wait for it to be processed.")
                    case _:
                        await message.channel.send("An error occurred while processing your request. Please try again later.")

        @self._bot.event
        async def on_member_remove(member):
            if LOCK_ON_LEAVE:
                guild = member.guild
                botMessageChannel = discord.utils.get(guild.text_channels, name=BOT_CHANNEL) 

                if botMessageChannel:
                    botMessageChannelMessage = self._lock_account(member.name, member.id)
                    await botMessageChannel.send(botMessageChannelMessage)