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
from ASSEMBLY_bot_files.ASSEMBLY_botSettings import BOT_CHANNEL, ROLE_TO_PING

SECONDS_IN_DAY = 86400

class AssemblyBot(BotHelpers, BotCommands, BotEvents):
    """
    Main class that inherits from:
      - BotHelpers (utility methods)
      - BotCommands (commands)
      - BotEvents (event listeners)
    """
    def __init__(self, discordToken, dbConfig):
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
                pool_size=5,  # Number of connections in the pool
                **dbConfig
            )
            print(f"{self._MODULE_NAME}: MySQL connection pool created successfully.")
        except Error as e:
            print(f"{self._MODULE_NAME}: Failed to create connection pool: {e}")
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



