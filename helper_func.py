import asyncio
import re
import base64

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import ChatJoinRequest, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant
from pyrogram.errors import FloodWait

from config import FORCE_SUB_CHANNEL, FORCE_SUB_CHANNEL2, ADMINS


VERIFIED_USERS = set()


@Client.on_chat_join_request()
async def join_request_verify(client, request: ChatJoinRequest):
    user_id = request.from_user.id
    VERIFIED_USERS.add(user_id)


async def get_request_link(client, channel_id):
    link = await client.create_chat_invite_link(
        chat_id=channel_id,
        creates_join_request=True
    )
    return link.invite_link


async def is_subscribed(filter, client, update):
    user_id = update.from_user.id

    if user_id in ADMINS:
        return True

    if user_id not in VERIFIED_USERS:
        return False

    for channel in [FORCE_SUB_CHANNEL, FORCE_SUB_CHANNEL2]:
        if not channel:
            continue
        try:
            member = await client.get_chat_member(channel, user_id)
            if member.status not in (
                ChatMemberStatus.OWNER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.MEMBER
            ):
                return False
        except UserNotParticipant:
            return False

    return True


subscribed = filters.create(is_subscribed)


@Client.on_message(filters.private & ~subscribed)
async def not_verified(client, message):
    buttons = []

    if FORCE_SUB_CHANNEL:
        link1 = await get_request_link(client, FORCE_SUB_CHANNEL)
        buttons.append([InlineKeyboardButton("Verify Channel 1", url=link1)])

    if FORCE_SUB_CHANNEL2:
        link2 = await get_request_link(client, FORCE_SUB_CHANNEL2)
        buttons.append([InlineKeyboardButton("Verify Channel 2", url=link2)])

    await message.reply(
        "You are not verified. Send join request to continue.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@Client.on_message(filters.private & subscribed)
async def verified_user(client, message):
    await message.reply("Verified")


async def encode(string):
    string_bytes = string.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    return base64_bytes.decode("ascii").strip("=")


async def decode(base64_string):
    base64_string = base64_string.strip("=")
    base64_bytes = (base64_string + "=" * (-len(base64_string) % 4)).encode("ascii")
    return base64.urlsafe_b64decode(base64_bytes).decode("ascii")


async def get_messages(client, message_ids):
    messages = []
    total = 0

    while total < len(message_ids):
        temp_ids = message_ids[total:total + 200]
        try:
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=temp_ids
            )
        except FloodWait as e:
            await asyncio.sleep(e.x)
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=temp_ids
            )
        except Exception:
            msgs = []

        messages.extend(msgs)
        total += len(temp_ids)

    return messages


async def get_message_id(client, message):
    if message.forward_from_chat:
        if message.forward_from_chat.id == client.db_channel.id:
            return message.forward_from_message_id
        return 0

    if message.forward_sender_name:
        return 0

    if message.text:
        pattern = r"https://t.me/(?:c/)?(.*)/(\d+)"
        match = re.match(pattern, message.text)
        if not match:
            return 0

        channel_id = match.group(1)
        msg_id = int(match.group(2))

        if channel_id.isdigit():
            if f"-100{channel_id}" == str(client.db_channel.id):
                return msg_id
        else:
            if channel_id == client.db_channel.username:
                return msg_id

    return 0


def get_readable_time(seconds: int) -> str:
    count = 0
    time_list = []
    suffixes = ["s", "m", "h", "days"]

    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(f"{int(result)}{suffixes[count-1]}")
        seconds = int(remainder)

    if len(time_list) == 4:
        return f"{time_list.pop()}, " + ":".join(reversed(time_list))

    return ":".join(reversed(time_list))
