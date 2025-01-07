import discord
from ASSEMBLY_bot_files.ASSEMBLY_botSettings import REQUEST_CHANNEL, ROLE_TO_PING, LOCK_ON_LEAVE, BOT_CHANNEL

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
            if isinstance(message.channel, discord.TextChannel) and message.channel.name == REQUEST_CHANNEL and not message.author.bot:
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
                        role = discord.utils.get(message.guild.roles, name=ROLE_TO_PING)
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
                        role = discord.utils.get(message.guild.roles, name=ROLE_TO_PING)
                        thread = await message.create_thread(name="DM Disabled", auto_archive_duration=1440)  # Auto-archive after 24 hours
                        await thread.send(f'{message.author.mention}, your DMs are disabled. Please enable DMs and try again.\nIf you need assistance, please @ a {ROLE_TO_PING}.')
                
                db_connection.close()

        @self._bot.event
        async def on_member_remove(member):
            if LOCK_ON_LEAVE:
                guild = member.guild
                botMessageChannel = discord.utils.get(guild.text_channels, name=BOT_CHANNEL) 

                if botMessageChannel:
                    botMessageChannelMessage = self._lock_account(member.name, member.id)
                    await botMessageChannel.send(botMessageChannelMessage)