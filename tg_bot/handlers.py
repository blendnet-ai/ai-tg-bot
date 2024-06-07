import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram.constants import ParseMode
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CallbackContext,
)
from tg_bot.utils import (
    is_bot_mentioned,
    create_agent_if_not_existing,
    delete_agent,
    reset_agent_persona,
    split_text_into_chunks,
)
from tg_bot.memgpt_wrapper import MemGPTWrapper
import traceback
import html
import json
import telegram

logger = logging.getLogger(__name__)

user_semaphores = {}
user_tasks = {}

gpt_wrapper = MemGPTWrapper()


async def post_init(application: Application):
    await application.bot.set_my_commands(
        [
            BotCommand("/new", "Start new dialog"),
            BotCommand(
                "/reset_persona",
                "Resets the agent persona (Do this after changing it in the DB)",
            ),
        ]
    )


async def reset_persona_handle(update: Update, context: CallbackContext):
    await reset_agent_persona(update.message.chat_id)
    await update.message.reply_text(
        "The agent persona has been reset!", parse_mode=ParseMode.HTML
    )


async def start_handle(update: Update, context: CallbackContext):
    reply_text = "Hi! I'm Disha, your TA, here to help you in your studies.\n\n"
    _, error_msg = await create_agent_if_not_existing(update, is_start=True)
    if error_msg:
        await update.message.reply_text(error_msg, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)


async def edited_message_handle(update: Update, context: CallbackContext):
    if update.edited_message.chat.type == "private":
        text = "🥲 Unfortunately, message <b>editing</b> is not supported"
        await update.edited_message.reply_text(text, parse_mode=ParseMode.HTML)


async def is_previous_message_not_answered_yet(update: Update):

    user_id = update.message.from_user.id
    if user_semaphores[user_id].locked():
        text = "⏳ Please <b>wait</b> for a reply to the previous message\n"
        text += "Or you can /cancel it"
        await update.message.reply_text(
            text, reply_to_message_id=update.message.id, parse_mode=ParseMode.HTML
        )
        return True
    else:
        return False


async def message_handle(update: Update, context: CallbackContext):
    # check if bot was mentioned (for group chats)
    if not await is_bot_mentioned(update, context):
        return
    user_id = update.message.from_user.id
    if user_id not in user_semaphores:
        user_semaphores[user_id] = asyncio.Semaphore(1)

    # check if message is edited
    if update.edited_message is not None:
        await edited_message_handle(update, context)
        return

    _message = update.message.text
    if _message.lower().startswith("delete,"):
        agent_deleted, deleted_error_txt = await delete_agent(
            _message, update.message.chat_id
        )
        if agent_deleted:
            await update.message.reply_text(
                "Agent has been deleted. Please register again."
            )
        else:
            await update.message.reply_text(
                f"Couldn't delete agent. \n {deleted_error_txt}"
            )
        return

    # remove bot mention (in group chats)
    if update.message.chat.type != "private":
        _message = _message.replace("@" + context.bot.username, "").strip()

    memgpt_agent, error_msg = await create_agent_if_not_existing(update)
    if await is_previous_message_not_answered_yet(update):
        return

    async def message_handle_fn():
        try:
            # send placeholder message to user
            placeholder_message = await update.message.reply_text("...")
            if error_msg:
                await context.bot.edit_message_text(
                    error_msg,
                    chat_id=placeholder_message.chat_id,
                    message_id=placeholder_message.message_id,
                )
                return
            # send typing action
            await update.message.chat.send_action(action="typing")
            if _message is None or len(_message) == 0:
                await update.message.reply_text(
                    "🥲 You sent <b>empty message</b>. Please, try again!",
                    parse_mode=ParseMode.HTML,
                )
                return

            response = gpt_wrapper.generate_response(memgpt_agent.id, _message)

            try:
                await context.bot.edit_message_text(
                    response,
                    chat_id=placeholder_message.chat_id,
                    message_id=placeholder_message.message_id,
                )
            except telegram.error.BadRequest as e:
                if str(e).startswith("Message is not modified"):
                    logger.error(e)

        except asyncio.CancelledError as e:
            logger.error(f"Got CancelledError during completion: {e}")
            raise

        except Exception as e:
            error_text = f"Something went wrong during completion. Reason: {e}"
            logger.error(error_text)
            await update.message.reply_text(error_text)
            return

    async with user_semaphores[user_id]:
        task = asyncio.create_task(message_handle_fn())
        user_tasks[user_id] = task
        try:
            await task
        except asyncio.CancelledError:
            await update.message.reply_text("✅ Canceled", parse_mode=ParseMode.HTML)
        finally:
            if user_id in user_tasks:
                del user_tasks[user_id]


async def error_handle(update: Update, context: CallbackContext):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    try:
        tb_list = traceback.format_exception(
            None, context.error, context.error.__traceback__
        )
        tb_string = "".join(tb_list)
        update_str = update.to_dict() if isinstance(update, Update) else str(update)
        message = (
            f"An exception was raised while handling an update\n"
            f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
            "</pre>\n\n"
            f"<pre>{html.escape(tb_string)}</pre>"
        )
        # split text into multiple messages due to 4096 character limit
        for message_chunk in split_text_into_chunks(message, 4096):
            try:
                await context.bot.send_message(
                    update.effective_chat.id, message_chunk, parse_mode=ParseMode.HTML
                )
            except telegram.error.BadRequest:
                # answer has invalid characters, so we send it without parse_mode
                await context.bot.send_message(update.effective_chat.id, message_chunk)
    except Exception:
        await context.bot.send_message(
            update.effective_chat.id, "Some error in error handler"
        )
