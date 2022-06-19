# bot.py
# A Discord bot that can send voice messages to a voice channel using user
# input

# Made by JJeeff248

# Imports
import os
import sqlite3
from typing import Dict, Tuple
import xml.etree.ElementTree as ET
import logging
from cgitb import handler

import azure.cognitiveservices.speech as speechsdk

import discord
from discord.ext import commands
from discord.ext.commands.context import Context
from discord import Activity, app_commands
from discord import FFmpegPCMAudio

from credentials import TOKEN           # Bot token
from credentials import APPLCATION_ID   # Discord application ID
from credentials import SERVICE_KEY     # Azure Speech API key
from credentials import SERVICE_REGION  # Azure Speech API region


def get_voices() -> Dict[str, list[str]]:
    """Gets all the voices available from the Azure API (Stored in database)
    :return: A dictionary of all the voices available
    """

    db = sqlite3.connect("User_Options.db")
    cursor = db.cursor()
    cursor.execute("SELECT * FROM Voices")

    voice_list = cursor.fetchall()

    voices = {}
    for voice in voice_list:
        voices[voice[0]] = [voice[1], voice[2], voice[3]]

    return voices


async def get_user(user_id: int) -> Tuple[str, int]:
    """Checks for the user in the database and returns their settings.
    Adds the user if they don't exist.

    :param user_id: The user's id
    :return: The users selected voice and speed
    """
    # Try find the user in the database
    db = sqlite3.connect("User_Options.db")
    cursor = db.cursor()
    cursor.execute("SELECT * FROM UserSettings WHERE UserID = ?", [user_id])

    result = cursor.fetchone()

    # If the user isn't in the database, add them with default values
    if result is None:
        cursor.execute("INSERT INTO UserSettings VALUES (?, ?, ?)",
                       [user_id, "en-US-JennyNeural", "default"])
        db.commit()
        cursor.execute(
            "SELECT * FROM UserSettings WHERE UserID = ?", [user_id])

        result = cursor.fetchone()

    db.close()

    return result[1], result[2]


async def update_voice(user_id: int, voice: str) -> None:
    """Updates the user's voice in the database

    :param user_id: The user's id
    :param voice: The user's voice
    """
    await get_user(user_id)  # Ensures the user is in the database.

    db = sqlite3.connect("User_Options.db")
    cursor = db.cursor()
    cursor.execute("UPDATE UserSettings SET VoiceID = ? WHERE UserID = ?",
                   [voice, user_id])
    db.commit()
    db.close()


async def update_speed(user_id: int, speed: int) -> None:
    """Updates the user's speed in the database

    :param user_id: The user's id
    :param speed: The user's speed
    """
    await get_user(user_id)  # Ensures the user is in the database.

    db = sqlite3.connect("User_Options.db")
    cursor = db.cursor()
    cursor.execute("UPDATE UserSettings SET Speed = ? WHERE UserID = ?",
                   [speed, user_id])
    db.commit()
    db.close()


# Setup options for commands
voices = get_voices()
speed_options = {"Extra slow": "x-slow",
                 "Slow": "slow",
                 "Medium": "medium",
                 "Fast": "fast",
                 "Extra fast": "x-fast",
                 "Default": "default"}


# Logger setup
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(
    filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter(
    '%(asctime)s:%(levelname)s:%(name)s:%(message)s'))
logger.addHandler(handler)


# Bot client setup
intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(
    intents=intents,
    application_id=APPLCATION_ID,
    command_prefix="\\",
    activity=Activity(
        type=discord.ActivityType.playing,
        name="your sweet words"))

client.voice_channel = None
client.queue = []
client.played_messages = []
client.last_user = None


# Speech setup
speech_config = speechsdk.SpeechConfig(
    subscription=SERVICE_KEY,
    region=SERVICE_REGION)

ssml_tree = ET.parse("ssml.xml")
ssml_root = ssml_tree.getroot()


def play_queue(*args) -> None:
    """Loops through the queue and plays the next file"""
    client.played_messages.append(client.queue.pop(0))

    if len(client.queue) > 0:
        client.voice_channel.play(FFmpegPCMAudio(
            f"{client.queue[0]}"), after=play_queue)
    elif client.voice_channel is None or not client.voice_channel.is_playing():
        clean_files()


def clean_files() -> None:
    """Cleans up the files in the queue"""
    if client.voice_channel is None or not client.voice_channel.is_playing():
        for file in client.played_messages:
            os.remove(file)
        client.played_messages = []


@client.event
async def on_ready() -> None:
    """Runs when the bot has started and is ready to use"""
    logger.info(f"Logged in as {client.user} (ID: {client.user.id})")

    print(f"Logged in as {client.user} (ID: {client.user.id})")
    print("------")


@client.event
async def on_command_error(ctx: Context, error: commands.CommandError) -> None:
    """Handles errors in the command system"""
    if isinstance(
            error,
            commands.PrivateMessageOnly) or isinstance(
            error,
            commands.NotOwner):
        logger.info(
            f"{ctx.author} tried to use a {ctx.command} in {ctx.guild}")
    else:
        logger.error(
            f"{ctx.author} tried to use a {ctx.command} in {ctx.guild} and it failed:\n{error}")


@client.tree.command(name="ping")
async def ping(interaction: discord.Interaction) -> None:
    """Returns the latency of the bot"""
    await interaction.response.send_message(f"Pong! {round(client.latency * 1000)}ms")
    logger.info(f"Ping: {round(client.latency * 1000)}ms")


@client.tree.command(name="join")
async def join(interaction: discord.Interaction) -> None:
    """Joins the voice channel you're in"""

    if client.voice_channel is None and interaction.user.voice is not None:
        await get_user(interaction.user.id)
        client.voice_channel = await client.get_channel(interaction.user.voice.channel.id).connect()

        await interaction.response.send_message(f"Joined {client.voice_channel.channel.name}")
        logger.info(
            f"Join: Joined {client.voice_channel.channel.name} in {client.voice_channel.channel.guild.name}")
    elif client.voice_channel is not None:
        await interaction.response.send_message("I'm already in a voice channel", ephemeral=True)
        logger.info(
            f"Join: Asked to join a voice channel, but I'm already in one")
    else:
        await interaction.response.send_message("You need to be in a voice channel for me to join", ephemeral=True)
        logger.info(
            f"Join: Asked to join a voice channel, but user isn't in one")


@client.tree.command(name="leave")
async def leave(interaction: discord.Interaction) -> None:
    """Leaves the voice channel"""

    if client.voice_channel is not None and client.voice_channel.channel == interaction.user.voice.channel:
        await client.voice_channel.disconnect()
        client.voice_channel = None

        await interaction.response.send_message("Left the voice channel")
        logger.info(f"Leave: Left the voice channel")
    elif interaction.user.voice.channel is None or client.voice_channel is not interaction.user.voice.channel:
        await interaction.response.send_message(f"You need to be in the same channel as me to use that command", ephemeral=True)
        logger.info(
            f"Leave: Asked to leave a voice channel, but user isn't my one")
    else:
        await interaction.response.send_message("I'm not in a voice channel", ephemeral=True)
        logger.info(
            f"Leave: Asked to leave a voice channel, but I'm not in one")


@client.tree.command(name="voice")
async def voice_select(interaction: discord.Interaction, voice: str) -> None:
    """Select a voice to use for the bot"""

    if voice in voices.keys():
        await update_voice(interaction.user.id, voice)
        await interaction.response.send_message(f"Set your voice to {voices[voice][0]}", ephemeral=True)
        logger.info(
            f"Voice: Set voice to {voices[voice][0]} for user {interaction.user.id}")
    else:
        await interaction.response.send_message(f"{voice} is not a valid voice. Please select from the list", ephemeral=True)
        logger.info(
            f"Voice: User {interaction.user.id} tried to set their voice to {voice}")


@voice_select.autocomplete("voice")
async def autocomplete_callback(interaction: discord.Interaction, current: str) -> list[app_commands.Choice]:
    voice_options = []
    for voice, values in voices.items():
        option = f"{values[0].title()}    -    ({values[1]}, {values[2]})"
        expanded_option = f"{values[0]} {values[1]} {values[2]}".lower()
        if expanded_option.__contains__(current.lower()):
            voice_options.append(app_commands.Choice(
                name=option, value=voice))

    return voice_options


@client.tree.command(name="speed")
async def set_speed(interaction: discord.Interaction, speed: str) -> None:
    """Set the speed of your text to speech"""
    if speed in speed_options.keys():
        await update_speed(interaction.user.id, speed_options[speed])
        await interaction.response.send_message(f"Set your speed to {speed}", ephemeral=True)
        logger.info(
            f"Speed: Set speed to {speed} for user {interaction.user.id}")
    else:
        await interaction.response.send_message(f"{speed} is not a valid speed. Please select from the list", ephemeral=True)
        logger.info(
            f"Speed: User {interaction.user.id} tried to set their speed to {speed}")


@set_speed.autocomplete("speed")
async def autocomplete_callback(interaction: discord.Interaction, current: str) -> list[app_commands.Choice]:
    autocomplete_options = []

    for option in speed_options.keys():
        if option.lower().__contains__(current.lower()):
            autocomplete_options.append(app_commands.Choice(
                name=option, value=option))

    return autocomplete_options


@client.tree.command(name="say")
async def say(interaction: discord.Interaction, text: str) -> None:
    """Speaks the given text"""

    if client.voice_channel is None or client.voice_channel.channel != interaction.user.voice.channel:
        await interaction.response.send_message("You need to be in the same "
                                                + "voice channel as me to use `/say` command", ephemeral=True)
        logger.info(
            f"Say: User {interaction.user.id} tried to speak, but they're not in the voice channel")
        return

    if client.last_user != interaction.user.id:
        text = interaction.user.display_name + " said: " + text
        client.last_user = interaction.user.id

    await interaction.response.defer()

    # Get the user's voice and speed
    voice_id, speed = await get_user(interaction.user.id)

    ssml_root[0].set("name", voice_id)
    ssml_root[0][0].set("rate", speed)
    ssml_root[0][0].text = text

    with open("ssml.xml", "wb") as f:
        f.write(ET.tostring(ssml_root))

    # Set the engines voice and speed
    audio_config = speechsdk.audio.AudioOutputConfig(
        filename=f"audio_files/{len(client.queue)}.mp3")
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config, audio_config=audio_config)

    with open("ssml.xml") as f:
        ssml_string = open("ssml.xml").read()
        f.close()

    result = synthesizer.speak_ssml_async(ssml_string).get()

    stream = speechsdk.AudioDataStream(result)
    stream.save_to_wav_file(f"audio_files/{len(client.queue)}.mp3")

    client.queue.append(f"audio_files/{len(client.queue)}.mp3")

    # If the bot isn't playing a message send the message
    if client.voice_channel.is_playing() is False:
        client.voice_channel.play(FFmpegPCMAudio(
            "audio_files/0.mp3"), after=play_queue)
        await interaction.followup.send(f"Said: {text}")
    else:
        await interaction.followup.send(f"Queued: {text}")


@client.tree.command(name="remove-data")
async def remove_data(interaction: discord.Interaction) -> None:
    """Delete your user from the database (Discord user ID, voice, speed)"""

    db = sqlite3.connect("User_Options.db")
    cursor = db.cursor()

    cursor.execute("DELETE FROM UserSettings WHERE UserID = ?",
                   (interaction.user.id,))
    db.commit()
    db.close()

    await interaction.response.send_message("Removed your data", ephemeral=True)


@client.command()
@commands.is_owner()
@commands.dm_only()
async def ping(ctx: Context) -> None:
    """Pong!"""
    await ctx.send(f"Pong! {round(client.latency * 1000)}ms")


@client.command()
@commands.is_owner()
@commands.dm_only()
async def sync(ctx: Context) -> None:
    fmt = await ctx.bot.tree.sync()
    await ctx.message.delete()
    logger.info(f"Synced {len(fmt)} commands.")


@client.command()
@commands.is_owner()
@commands.dm_only()
async def remove_global(ctx: Context) -> None:
    await client.http.bulk_upsert_global_commands(client.application_id, [])
    await ctx.message.delete()
    logger.info("Removed global commands")


@client.command()
@commands.is_owner()
@commands.dm_only()
async def remove_guild(ctx: Context) -> None:
    await client.http.bulk_upsert_guild_commands(client.application_id, ctx.guild.id, [])
    await ctx.message.delete()
    logger.info(f"Removed guild commands from {ctx.guild.name}")


client.run(TOKEN)
