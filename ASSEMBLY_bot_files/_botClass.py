import asyncio
import discord
from discord.ext import commands
import mysql.connector
import mysql.connector.pooling
from mysql.connector import Error
import sys
import time
from ASSEMBLY_bot_files._events import BotEvents
from ASSEMBLY_bot_files._commands import BotCommands
from ASSEMBLY_bot_files._helpers import BotHelpers
from ASSEMBLY_bot_files.ASSEMBLY_botSettings import BOT_CHANNEL, ROLE_TO_PING, RSVD_OBJ_ID_START

SECONDS_IN_DAY = 86400

class AssemblyBot(BotHelpers, BotCommands, BotEvents):
    """
    Main class that inherits from:
      - BotHelpers (utility methods)
      - BotCommands (commands)
      - BotEvents (event listeners)
    """
    def __init__(self, discordToken, dbConfig, dbConfigBlu):
        """
        Initializes the AssemblyBot instance.

        Parameters:
            discordToken (str): Discord bot token.
            dbConfig (dict): Dictionary with MySQL connection information. Example:
            {
                'host': 'localhost',
                'user': 'darkflame',
                'password': 'abc123',
                'database': 'darkflame'
            }
            dbConfigBlu (dict): Dictionary with MySQL connection information for BLU.

        Returns:
            None
        """
        self._MODULE_NAME = "[ASSEMBLY_bot_discord]"

        self.__discordToken = discordToken

        if dbConfig is None:
            print(f"{self._MODULE_NAME}: ERROR: No database configuration provided")
            sys.exit(1)

        # Set up database connection pool
        try:
            self._connection_pool =  mysql.connector.pooling.MySQLConnectionPool(
                pool_name="assembly_bot_pool",
                pool_size=10,  # Number of connections in the pool
                **dbConfig
            )
            print(f"{self._MODULE_NAME}: MySQL connection pool created successfully.")
        except Error as e:
            print(f"{self._MODULE_NAME}: Failed to create connection pool: {e}")
            sys.exit(1)

        # Set up BLU database connection pool
        try:
            self._blu_connection_pool =  mysql.connector.pooling.MySQLConnectionPool(
                pool_name="assembly_bot_blu_pool",
                pool_size=10,  # Number of connections in the pool
                **dbConfigBlu
            )
            print(f"{self._MODULE_NAME}: MySQL BLU connection pool created successfully.")
        except Error as e:
            print(f"{self._MODULE_NAME}: Failed to create BLU connection pool: {e}")
            sys.exit(1)

        super().__init__()

        # Setup the bot
        self._intents = discord.Intents.default()
        self._intents.message_content = True
        self._intents.guilds = True
        self._intents.members = True
        self._bot = commands.Bot(command_prefix="/", intents=self._intents)

        # Set up commands and events
        self._setup_commands()
        self._setup_events()

        # Setup BLU migration table
        db_connection = self._get_db_connection()
        if db_connection:
            cursor = db_connection.cursor()
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS blu_transfers ("
                "id INT AUTO_INCREMENT PRIMARY KEY, "
                "discord_uuid VARCHAR(255) DEFAULT NULL, "
                "account_id INT DEFAULT NULL, "
                "blu_account_id INT DEFAULT NULL, "
                "migration_state INT DEFAULT 0, "
                "attempts INT DEFAULT 0, "
                "chosen_chars TEXT DEFAULT NULL, "
                "error_state INT DEFAULT 0 "
                ");"
            )
            db_connection.commit()
            cursor.close()
            db_connection.close()
        else:
            print(f"{self._MODULE_NAME}: ERROR: No mysql connection, unable to setup BLU migration table")

        # Setup migration_object_ids table
        db_connection = self._get_db_connection()
        if db_connection:
            cursor = db_connection.cursor()
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS migration_object_ids ("
                "next_avail_id INT DEFAULT 0 "
                ");"
            )
            db_connection.commit()

            cursor.execute("SELECT COUNT(*) FROM migration_object_ids")
            count = cursor.fetchone()[0]
            if count == 0:
                cursor.execute("INSERT INTO migration_object_ids (next_avail_id) VALUES (%s)", (RSVD_OBJ_ID_START,))
                db_connection.commit()
            cursor.close()
            db_connection.close()
        else:
            print(f"{self._MODULE_NAME}: ERROR: No mysql connection, unable to setup BLU migration table")

    def start_discord_bot(self):
        """
        Start the bot 
        """
        self._bot_started = True

        try:
            self._bot.run(self.__discordToken)
        except Exception as e:
            print(f"{self._MODULE_NAME}: Bot failed: {e}")
            self._bot_started = False
            sys.exit(1)

    def send_discord_message(self, message):
        """
        Thread-safe method to send a Discord message to the bot channel.

        Parameters:
            message (str): The message to send to the Discord bot channel.

        Returns:
            None
        """
        # Wait until the bot is ready
        while not self._bot.is_ready():
            time.sleep(1)

        # Get the channel
        channel = discord.utils.get(self._bot.get_all_channels(), name=BOT_CHANNEL)

        if channel is None:
            print(f"{self._MODULE_NAME}: ERROR: Channel '{BOT_CHANNEL}' not found! Message not sent.")
            return

        # Prepare the coroutine to send a message
        coroutine = channel.send(message)

        # Schedule the coroutine on the bot's event loop
        asyncio.run_coroutine_threadsafe(coroutine, self._bot.loop)

    def report_user_offenses(self, users_to_report):
        """
        Wrapper for _report_user_offenses()

        Parameters:
            users_to_report (dict): A dictionary where keys are user IDs (int) and values are lists of offenses.
            Example:
                see check_for_offenses() for example

        Returns:
            None: This method does not return a value.
        """
        # Schedule the asynchronous report_user_offenses method in the bot's event loop
        future = asyncio.run_coroutine_threadsafe(
            self._report_user_offenses(users_to_report),
            self._bot.loop
        )
        try:
            # wait for the result (blocking)
            future.result()
        except Exception as e:
            print(f"{self._MODULE_NAME}: ERROR while reporting offenses: {e}")

    async def _report_user_offenses(self, users_to_report):
        """
        Report user offenses to the bot channel with interactive buttons.
        """
        if not self._bot_started:
            print(f"{self._MODULE_NAME}: ERROR: Bot not started, unable to check for offenses")
            return

        # Wait for the bot to be ready
        while not self._bot.is_ready():
            print(f"{self._MODULE_NAME}: Waiting for bot to be ready...")
            await asyncio.sleep(5)

        # Get the bot channel
        channel = discord.utils.get(self._bot.get_all_channels(), name=BOT_CHANNEL)

        if channel is None:
            print(f"{self._MODULE_NAME}: ERROR: Channel '{BOT_CHANNEL}' not found! Unable to send offenses report.")
            return

        # Send a separate embed card for each user
        for user, offenses in users_to_report.items():
            user_obj = await self._bot.fetch_user(user)
            user_name = user_obj.name if user_obj else user
            user_mention = user_obj.mention if user_obj else user

            user_embed = discord.Embed(
                title=f"{user_name} - Offenses Report",
                description=f"The user {user_mention} has reached the notification threshold for number of offenses.",
                color=discord.Color.yellow()
            )

            # If there are more than 25 offenses, notify the user to manually view them
            if len(offenses) > 25: # 25 is the max number of fields a Discord embed can have
                user_embed.description += (
                    f"\n\n__**Note:**__ This user has more than 25 offenses. "
                    f"Please review the full list manually using commands.\n\n"
                )
                await channel.send(embed=user_embed) # Can use await here b/c we are in an async function being ran in the bot event loop
                continue

            # Add each offense as a separate field
            for idx, offense in enumerate(offenses, start=1):
                formatted_offense = (
                    f"{offense['offense']}\n\n"
                    f"__*Type:*__ {offense['type']}\n"
                    f"__*Timestamp:*__ {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(offense['timestamp']))} UTC\n"
                    f"__*Action Taken:*__ {offense['action-taken']}\n\n"
                )

                user_embed.add_field(
                    name=f"Offense #{idx}",
                    value=formatted_offense,
                    inline=False
                )

            # Create a view with buttons for each offense
            view = self.OffenseView(user_id=user, bot_instance=self, offenses=offenses)

            # Send the embed with the view (save the view to the message for later interaction)
            view.message = await channel.send(embed=user_embed, view=view) # Can use await here b/c we are in an async function being ran in the bot event loop

            await asyncio.sleep(0.3)
        
        # Mention the moderator role to notify about potential violations
        guild = channel.guild
        role = discord.utils.get(guild.roles, name=ROLE_TO_PING)

        if role:
            notification_message = f"{role.mention}, please review the offenses reported above."
            coroutine = channel.send(notification_message)
            asyncio.run_coroutine_threadsafe(coroutine, self._bot.loop)
        else:
            print(f"{self._MODULE_NAME}: ERROR: Role {ROLE_TO_PING} not found! Unable to mention.")

    async def _send_migration_selection(self, user_obj, nu_chars, blu_chars, available_slots):
        """Send an interactive selection card to the user for selective migration.

        Parameters
        ----------
        user_obj: discord.User
            The Discord user to send the card to.
        nu_chars: list
            List of tuples ``(name, id)`` for the user's NU characters.
        blu_chars: list
            List of tuples ``(name, id)`` for the user's BLU characters.
        available_slots: int
            Number of free character slots currently available on NU.
        """

        if not self._bot_started:
            print(f"{self._MODULE_NAME}: ERROR: Bot not started, unable to send migration selection")
            return

        embed = discord.Embed(
            title="BLU Migration",
            description="Select which characters you wish to migrate.",
            color=discord.Color.blue(),
        )

        if nu_chars:
            embed.add_field(
                name="Your NU Characters",
                value="\n".join([name for name, _ in nu_chars]),
                inline=False,
            )

        embed.add_field(
            name="Your BLU Characters",
            value="\n".join([name for name, _ in blu_chars]) or "None",
            inline=False,
        )

        view = self.MigrationSelectionView(
            user_obj.id,
            nu_chars,
            blu_chars,
            available_slots,
            self,
        )
        message = await user_obj.send(embed=embed, view=view)
        view.message = message  # Save message for later edits (timeout/confirm)
        self.active_migration_views.add(view)


    ###########################
    # Discord UI Classes
    ###########################
    class OffenseView(discord.ui.View):
        """
        View for displaying offense buttons and a "Dismiss All" button.
        """
        def __init__(self, user_id, offenses, bot_instance, timeout=SECONDS_IN_DAY):
            """
            Initialize the bot class with user-specific and bot-specific data, along with a timeout.

            Parameters:
                user_id (int): The unique identifier for the user.
                offenses (list): A list of offense obj associated with the user.
                bot_instance (object): The instance of the bot managing this user.
                timeout (int): Timeout in seconds before buttons are disabled. Defaults to SECONDS_IN_DAY.

            Returns:
                None: This method does not return a value.
            """
       
            super().__init__(timeout=timeout) # Timeout in seconds
            self.user_id = user_id
            self.offenses = offenses
            self.bot_instance = bot_instance

            # Dynamically create a button for each offense and add it to the view
            for idx, offense in enumerate(self.offenses, start=1):
                self.add_item(self.create_offense_button(idx, offense))

        async def on_timeout(self):
            """
            Handle what happens when the view times out.
            """
            # Disable all buttons in the view
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

            # Update the message to reflect the disabled buttons
            if hasattr(self, "message"):
                try:
                    await self.message.edit(view=self)
                except Exception as e:
                    print(f"{self._MODULE_NAME}: ERROR while editing the message on timeout: {e}")


        @discord.ui.button(label="Dismiss All Offenses", style=discord.ButtonStyle.red)
        async def btn_dismiss_all(self, interaction: discord.Interaction, button: discord.ui.Button):
            """
            Handle the "Dismiss All" button click.
            """
            # Disable the "Dismiss All" button
            button.disabled = True

            # Disable all "Dismiss Offense #" buttons
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

            # Update the message with the disabled buttons
            await interaction.message.edit(view=self)

            # Dismiss all offenses for the user
            if self.bot_instance._dismiss_all_offenses(self.user_id):
                await interaction.response.send_message(
                    f"All offenses for user <@{self.user_id}> `{self.user_id}` have been dismissed.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Failed to dismiss all offenses for user <@{self.user_id}> `{self.user_id}`.",
                    ephemeral=True
                )

        def create_offense_button(self, offense_idx, offense):
            """
            Create a button for a specific offense.
            """
            button = discord.ui.Button(
                label=f"Dismiss Offense #{offense_idx}",
                style=discord.ButtonStyle.green
            )

            async def callback(interaction: discord.Interaction):
                """
                Handle the button click for dismissing a specific offense.
                """

                # Disable the clicked button
                button.disabled = True

                # Disable the "Dismiss All" button
                for child in self.children:
                    if isinstance(child, discord.ui.Button) and child.label == "Dismiss All Offenses":
                        child.disabled = True

                # Update the message with the disabled button
                await interaction.message.edit(view=self)

                # Dismiss the specific offense
                if self.bot_instance._dismiss_offense(self.user_id, offense):
                    await interaction.response.send_message(
                        f"Offense #{offense_idx} for user <@{self.user_id}> `{self.user_id}` has been dismissed.",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"Failed to dismiss offense #{offense_idx} for user <@{self.user_id}> `{self.user_id}`.",
                        ephemeral=True
                    )

            # Assign the callback to the button
            button.callback = callback

            return button

    class MigrationSelectionView(discord.ui.View):
        """Interactive view for selecting migration options."""

        def __init__(self, user_id, nu_chars, blu_chars, available_slots, bot_instance, timeout=SECONDS_IN_DAY):
            super().__init__(timeout=timeout)
            self.user_id = user_id
            self.bot_instance = bot_instance
            self.available_slots = available_slots

            # Track selected options so they can persist after view edits
            self.selected_nu: set[str] = set()
            self.selected_blu: set[str] = set()

            # Build SelectOption lists for NU and BLU characters
            nu_options = [discord.SelectOption(label=name, value=str(cid)) for name, cid in nu_chars]
            blu_options = [discord.SelectOption(label=name, value=str(cid)) for name, cid in blu_chars]

            self.blu_char_count = len(blu_options)
            # Determine how many NU characters the user may delete and how many
            # BLU characters can be transferred initially
            max_delete = max(0, self.blu_char_count - available_slots)
            max_transfer = min(self.blu_char_count, max(1, available_slots))

            if nu_options and max_delete > 0:
                self.nu_select = discord.ui.Select(
                    placeholder="NU chars to delete",
                    options=nu_options,
                    min_values=0,
                    max_values=max_delete,
                )

                async def nu_callback(interaction: discord.Interaction):
                    # Update BLU transfer limit when NU selections change
                    self.selected_nu = set(self.nu_select.values)
                    new_max = min(
                        self.blu_char_count,
                        max(1, self.available_slots + len(self.nu_select.values)),
                    )
                    self.blu_select.max_values = new_max
                    self.blu_select.placeholder = f"BLU chars to transfer (max {new_max})"

                    # If the new limit is smaller than the current selection
                    # clear the BLU selection so the user can pick again
                    if len(self.selected_blu) > new_max:
                        # Clear stored selections and reset option defaults so
                        # nothing appears chosen when the view is re-rendered
                        self.selected_blu.clear()
                        for opt in self.blu_select.options:
                            opt.default = False

                    # Persist selections by updating option defaults
                    for opt in self.nu_select.options:
                        opt.default = opt.value in self.selected_nu
                    for opt in self.blu_select.options:
                        opt.default = opt.value in self.selected_blu
                    await interaction.response.edit_message(view=self)

                self.nu_select.callback = nu_callback
                self.add_item(self.nu_select)
            else:
                self.nu_select = None

            self.blu_select = discord.ui.Select(
                placeholder=f"BLU chars to transfer (max {max_transfer})",
                options=blu_options,
                min_values=1,
                max_values=max_transfer,
            )

            async def blu_callback(interaction: discord.Interaction):
                self.selected_blu = set(self.blu_select.values)
                await interaction.response.defer()

            self.blu_select.callback = blu_callback
            self.add_item(self.blu_select)

        def _disable_all_items(self):
            """Disable all interactive components in this view."""
            for child in self.children:
                child.disabled = True

            if hasattr(self, "message"):
                # Update the message with disabled components
                return self.message.edit(view=self)
            return None

        async def on_timeout(self):
            """Disable the view when it times out."""
            await self._disable_all_items()
            self.bot_instance.active_migration_views.discard(self)

        @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not self.bot_instance.migrations_enabled:
                await interaction.response.send_message(
                    "Migrations are currently disabled.", ephemeral=True
                )
                await self._disable_all_items()
                self.bot_instance.active_migration_views.discard(self)
                self.stop()
                return

            delete_ids = [char for char in self.selected_nu]
            transfer_ids = [char for char in self.selected_blu]
            allowed = self.available_slots + len(delete_ids)

            if len(transfer_ids) > allowed:
                await interaction.response.send_message(
                    f"❌ You selected {len(transfer_ids)} BLU character(s) but only have {allowed} slot(s) available.",
                    ephemeral=True,
                )
                return
            
            if len(transfer_ids) == 0:
                await interaction.response.send_message(
                    "❌ You must select at least one BLU character to transfer.",
                    ephemeral=True,
                )
                return

            data = {"delete_nu": delete_ids, "migrate_blu": transfer_ids}

            await interaction.response.defer()
            success = await asyncio.to_thread(
                self.bot_instance._set_user_migration_selection,
                self.user_id,
                data,
            )

            if success:
                await asyncio.to_thread(
                    self.bot_instance._set_user_transfer_state,
                    self.user_id,
                    self.bot_instance.migration_state.TRANSFER_QUEUED,
                )
                migration_request = {
                    "discord_uuid": self.user_id,
                    "selective_migration": True,
                }
                self.bot_instance.migration_queue.put(migration_request)
                msg = "Selection saved. Your migration will begin soon."

                # Disable the view so it cannot be used again
                await self._disable_all_items()
            else:
                msg = "Failed to save selection. Please contact a mythran."

            await interaction.followup.send(
                msg, ephemeral=interaction.guild is not None
            )
            self.bot_instance.active_migration_views.discard(self)
            self.stop()


    def __del__(self):
        """
        Destructor. Close the DB connection.
        """
        # Close all connections in the connection pool
        if hasattr(self, "_connection_pool") and self._connection_pool:
            while not self._connection_pool._cnx_queue.empty():
                connection = self._connection_pool._cnx_queue.get_nowait()
                if connection.is_connected():
                    connection.close()

        # Close the individual database connection if it exists
        if hasattr(self, "_dbConnection") and self._dbConnection.is_connected():
            self._dbConnection.close()



