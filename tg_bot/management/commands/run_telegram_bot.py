import dataclasses
import html
import uuid

from channels.db import database_sync_to_async
from django.core.management.base import BaseCommand
from django.test import RequestFactory
from memgpt import create_client
from memgpt.data_types import LLMConfig

from tg_bot.models import Agent, UserTelegramConfig, AgentConfig
from custom_auth.models import UserProfile
from practice.views import (
    PracticeQuestionView,
    SubmitQuestionView,
    PracticeQuestionEvaluation,
)
from rest_framework.test import force_authenticate
import json
import os
import telegram
import requests
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from django.contrib.auth.models import User
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
import traceback
from django.conf import settings

from telegram.constants import ParseMode
from telegram import (
    Update,
    User as TelegramUser,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
import logging

logger = logging.getLogger(__name__)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    AIORateLimiter,
    filters,
)

import asyncio

user_semaphores = {}
user_tasks = {}
Personas = {"default": "AI Helper"}
memgpt_client = create_client()


def get_now() -> datetime:
    required_timezone = "Asia/Kolkata"
    return datetime.now(ZoneInfo(required_timezone))


async def post_init(application: Application):
    await application.bot.set_my_commands(
        [
            BotCommand("/new", "Start new dialog"),
            BotCommand("/mode", "Select chat mode"),
            BotCommand("/retry", "Re-generate response for previous query"),
            BotCommand("/balance", "Show balance"),
            BotCommand("/settings", "Show settings"),
            BotCommand("/help", "Show help message"),
        ]
    )


HELP_MESSAGE = """Commands:
⚪ /retry – Regenerate last bot answer
⚪ /new – Start new dialog
⚪ /mode – Select chat mode
⚪ /settings – Show settings
⚪ /balance – Show balance
⚪ /help – Show help

🎨 Generate images from text prompts in <b>👩‍🎨 Artist</b> /mode
👥 Add bot to <b>group chat</b>: /help_group_chat
🎤 You can send <b>Voice Messages</b> instead of text
"""


def split_text_into_chunks(text, chunk_size):
    for i in range(0, len(text), chunk_size):
        yield text[i : i + chunk_size]


async def is_bot_mentioned(update: Update, context: CallbackContext):
    try:
        message = update.message

        if message.chat.type == "private":
            return True

        if message.text is not None and ("@" + context.bot.username) in message.text:
            return True

        if message.reply_to_message is not None:
            if message.reply_to_message.from_user.id == context.bot.id:
                return True
    except:
        return True
    else:
        return False


async def edited_message_handle(update: Update, context: CallbackContext):
    if update.edited_message.chat.type == "private":
        text = "🥲 Unfortunately, message <b>editing</b> is not supported"
        await update.edited_message.reply_text(text, parse_mode=ParseMode.HTML)


@database_sync_to_async
def create_agent_if_not_existing(update: Update, is_start=False):
    chat_id = update.message.chat_id
    try:
        agent = Agent.objects.get(telegram_chat_id=chat_id)
    except Agent.DoesNotExist:
        try:
            if is_start:
                message = update.message.text.replace("/start", "").strip()
            else:
                message = update.message.text
            otp, agent_config_name = message.lower().split("--")
            otp = int(otp)
            agent_config = AgentConfig.objects.get(name=agent_config_name)
        except AgentConfig.DoesNotExist:
            logger.exception(f"Agent config -<{agent_config_name}> doesn't exist")
            return (
                None,
                f"Agent config -<{agent_config_name}> doesn't exist"
                f"Available Personas are - {list(AgentConfig.objects.all().values_list('name',flat=True))}",
            )
        except Exception as e:
            logger.exception(f"Error while parsing first msg - {e}", e)
            return (
                None,
                "Send a msg in format of <otp>--<persona_name> to register your chat with your user. \n"
                "You can get your otp from the web app in profile section. Default persona can be chosen with"
                "<default>. \n"
                "Example start msg -> '111111--default_openai' .\n"
                f"Available Personas are - {list(AgentConfig.objects.all().values_list('name',flat=True))}",
            )
        else:
            user_profile_filter = UserProfile.objects.filter(otp=otp)
            if user_profile_filter.exists():
                user_profile = user_profile_filter.first()
                agent = Agent.objects.create(
                    user=user_profile.user_id, telegram_chat_id=chat_id
                )
                llm_config = LLMConfig(
                    model=agent_config.llm_config["model"],
                    model_endpoint_type=agent_config.llm_config["model_endpoint_type"],
                    model_endpoint=agent_config.llm_config["model_endpoint"],
                    context_window=agent_config.llm_config["context_window"],
                )
                memgpt_agent_state = memgpt_client.server.create_agent(
                    user_id=memgpt_client.user_id,
                    name=f"{agent_config.name}-{agent.user.id}",
                    persona=agent_config.persona_text,
                    llm_config=llm_config,
                    human=user_profile.get_user_details_for_memgpt(),
                    preset=agent_config.memgpt_preset_name,
                )
                # memgpt_agent_state = memgpt_client.create_agent(name=f"{agent_config.name}-{agent.user.id}",
                #                            persona=agent_config.persona_text,
                #                             llm_config=agent_config.llm_config,
                #                            human=user_telegram_config.get_user_details_for_memgpt())
                agent.memgpt_agent_id = memgpt_agent_state.id
                print("found memgpt agent id = ", memgpt_agent_state.id)
                agent.save()
            else:
                return None, "Wrong OTP."
    uuid_string = "{" + str(agent.memgpt_agent_id) + "}"

    memgpt_agent = memgpt_client.get_agent_config(agent_id=uuid.UUID(uuid_string))
    return memgpt_agent, ""


# async def register_user_if_not_exists(update: Update, context: CallbackContext, telegram_user: TelegramUser):
#     if not db.check_if_user_exists(user.id):
#         db.add_new_user(
#             user.id,
#             update.message.chat_id,
#             username=user.username,
#             first_name=user.first_name,
#             last_name= user.last_name
#         )
#         db.start_new_dialog(user.id)
#
#     if db.get_user_attribute(user.id, "current_dialog_id") is None:
#         db.start_new_dialog(user.id)
#
#     if user.id not in user_semaphores:
#         user_semaphores[user.id] = asyncio.Semaphore(1)
#
#     if db.get_user_attribute(user.id, "current_model") is None:
#         db.set_user_attribute(user.id, "current_model", config.models["available_text_models"][0])
#
#     # back compatibility for n_used_tokens field
#     n_used_tokens = db.get_user_attribute(user.id, "n_used_tokens")
#     if isinstance(n_used_tokens, int) or isinstance(n_used_tokens, float):  # old format
#         new_n_used_tokens = {
#             "gpt-3.5-turbo": {
#                 "n_input_tokens": 0,
#                 "n_output_tokens": n_used_tokens
#             }
#         }
#         db.set_user_attribute(user.id, "n_used_tokens", new_n_used_tokens)
#
#     # voice message transcription
#     if db.get_user_attribute(user.id, "n_transcribed_seconds") is None:
#         db.set_user_attribute(user.id, "n_transcribed_seconds", 0.0)
#
#     # image generation
#     if db.get_user_attribute(user.id, "n_generated_images") is None:
#         db.set_user_attribute(user.id, "n_generated_images", 0)


async def is_previous_message_not_answered_yet(
    update: Update, context: CallbackContext
):
    # await register_user_if_not_exists(update, context, update.message.from_user)

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


@database_sync_to_async
def delete_agent(message_text: str, chat_id: int):
    try:
        otp = message_text.split(",")[1]
        otp = int(otp)
        UserProfile.objects.get(otp=otp)
    except UserProfile.DoesNotExist:
        logger.exception(f"Wrong OTP")
        return False, "Wrong OTP."
    except Exception as e:
        logger.exception(f"Error while parsing first msg - {e}", e)
        return (
            None,
            "Send a msg in format of delete_agent,<your otp> to delete your current agent config. \n"
            "You can get your otp from the web app in profile section."
            f"Got error - {e}",
        )
    else:
        agent = Agent.objects.get(telegram_chat_id=chat_id)
        # agent_uuid = uuid.UUID("{"+agent.memgpt_agent_id+"}")
        memgpt_client.delete_agent(agent.memgpt_agent_id)
        agent.delete()
        return True, " "


async def message_handle(
    update: Update, context: CallbackContext, message=None, use_new_dialog_timeout=True
):
    # check if bot was mentioned (for group chats)
    print("got message in message handle", message)
    if not await is_bot_mentioned(update, context):
        return
    user_id = update.message.from_user.id
    if user_id not in user_semaphores:
        user_semaphores[user_id] = asyncio.Semaphore(1)
    # check if message is edited
    if update.edited_message is not None:
        await edited_message_handle(update, context)
        return
    print("update msg is ", update.message.text)
    _message = message or update.message.text
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

    if await is_previous_message_not_answered_yet(update, context):
        return

    print("got memgpt agent", memgpt_agent, error_msg)
    # chat_mode = db.get_user_attribute(user_id, "current_chat_mode")

    # if chat_mode == "artist":
    #     await generate_image_handle(update, context, message=message)
    #     return

    async def message_handle_fn():
        # new dialog timeout
        # if use_new_dialog_timeout:
        #     if (datetime.now() - db.get_user_attribute(user_id, "last_interaction")).seconds > config.new_dialog_timeout and len(db.get_dialog_messages(user_id)) > 0:
        #         db.start_new_dialog(user_id)
        #         await update.message.reply_text(f"Starting new dialog due to timeout (<b>{config.chat_modes[chat_mode]['name']}</b> mode) ✅", parse_mode=ParseMode.HTML)
        # db.set_user_attribute(user_id, "last_interaction", datetime.now())

        # in case of CancelledError
        n_input_tokens, n_output_tokens = 0, 0
        # current_model = db.get_user_attribute(user_id, "current_model")

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
            print("will try to generate memgpt response")
            response = memgpt_client.user_message(
                agent_id=memgpt_agent.id, message=_message
            )
            answer = ""
            print("got respnse", response)
            for r in response:
                if "assistant_message" in r:
                    answer += f"ASSISTANT:, {r['assistant_message']}\n"
                elif "internal_monologue" in r:
                    answer += f"THOUGHTS:, {r['internal_monologue']}\n"
            try:
                await context.bot.edit_message_text(
                    answer,
                    chat_id=placeholder_message.chat_id,
                    message_id=placeholder_message.message_id,
                )
            except telegram.error.BadRequest as e:
                if str(e).startswith("Message is not modified"):
                    logger.error(e)
                # else:
                #     await context.bot.edit_message_text(answer, chat_id=placeholder_message.chat_id, message_id=placeholder_message.message_id)

            # dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
            # parse_mode = {
            #     "html": ParseMode.HTML,
            #     "markdown": ParseMode.MARKDOWN
            # }[config.chat_modes[chat_mode]["parse_mode"]]
            #
            # chatgpt_instance = openai_utils.ChatGPT(model=current_model)
            # if config.enable_message_streaming:
            #     gen = chatgpt_instance.send_message_stream(_message, dialog_messages=dialog_messages, chat_mode=chat_mode)
            # else:
            #     answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed = await chatgpt_instance.send_message(
            #         _message,
            #         dialog_messages=dialog_messages,
            #         chat_mode=chat_mode
            #     )
            #
            #     async def fake_gen():
            #         yield "finished", answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed
            #
            #     gen = fake_gen()
            #
            # prev_answer = ""
            # async for gen_item in gen:
            #     status, answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed = gen_item
            #
            #     answer = answer[:4096]  # telegram message limit
            #
            #     # update only when 100 new symbols are ready
            #     if abs(len(answer) - len(prev_answer)) < 100 and status != "finished":
            #         continue
            #
            #     try:
            #         await context.bot.edit_message_text(answer, chat_id=placeholder_message.chat_id, message_id=placeholder_message.message_id, parse_mode=parse_mode)
            #     except telegram.error.BadRequest as e:
            #         if str(e).startswith("Message is not modified"):
            #             continue
            #         else:
            #             await context.bot.edit_message_text(answer, chat_id=placeholder_message.chat_id, message_id=placeholder_message.message_id)
            #
            #     await asyncio.sleep(0.01)  # wait a bit to avoid flooding
            #
            #     prev_answer = answer
            #
            # # update user data
            # new_dialog_message = {"user": _message, "bot": answer, "date": datetime.now()}
            # db.set_dialog_messages(
            #     user_id,
            #     db.get_dialog_messages(user_id, dialog_id=None) + [new_dialog_message],
            #     dialog_id=None
            # )
            #
            # db.update_n_used_tokens(user_id, current_model, n_input_tokens, n_output_tokens)

        except asyncio.CancelledError:
            # note: intermediate token updates only work when enable_message_streaming=True (config.yml)
            # db.update_n_used_tokens(user_id, current_model, n_input_tokens, n_output_tokens)
            raise

        except Exception as e:
            error_text = f"Something went wrong during completion. Reason: {e}"
            logger.error(error_text)
            await update.message.reply_text(error_text)
            return

        # send message if some messages were removed from the context
        # if n_first_dialog_messages_removed > 0:
        #     if n_first_dialog_messages_removed == 1:
        #         text = "✍️ <i>Note:</i> Your current dialog is too long, so your <b>first message</b> was removed from the context.\n Send /new command to start new dialog"
        #     else:
        #         text = f"✍️ <i>Note:</i> Your current dialog is too long, so <b>{n_first_dialog_messages_removed} first messages</b> were removed from the context.\n Send /new command to start new dialog"
        #     await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async with user_semaphores[user_id]:
        task = asyncio.create_task(message_handle_fn())
        user_tasks[user_id] = task

        try:
            await task
        except asyncio.CancelledError:
            await update.message.reply_text("✅ Canceled", parse_mode=ParseMode.HTML)
        else:
            pass
        finally:
            if user_id in user_tasks:
                del user_tasks[user_id]


async def error_handle(update: Update, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    try:
        # collect error message
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
    except:
        await context.bot.send_message(
            update.effective_chat.id, "Some error in error handler"
        )


async def start_handle(update: Update, context: CallbackContext, message=None):
    reply_text = "Hi! I'm Disha, your TA, here to help you in your studies.\n\n"
    # reply_text += HELP_MESSAGE
    print("got start message", update.message.text)
    memgpt_agent, error_msg = await create_agent_if_not_existing(update, is_start=True)
    if error_msg:
        await update.message.reply_text(error_msg, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)
    # await show_chat_modes_handle(update, context)


# def get_chat_mode_menu(page_index: int):
#     n_chat_modes_per_page = 5#config.n_chat_modes_per_page
#     # text = f"Select <b>chat mode</b> ({len(config.chat_modes)} modes available):"
#     text = f"Select <b>chat mode</b> 2 modes available):"
#     # buttons
#
#     chat_mode_keys = ["", ]#list(config.chat_modes.keys())
#     page_chat_mode_keys = chat_mode_keys[page_index * n_chat_modes_per_page:(page_index + 1) * n_chat_modes_per_page]
#
#     keyboard = []
#     for chat_mode_key in page_chat_mode_keys:
#         name = config.chat_modes[chat_mode_key]["name"]
#         keyboard.append([InlineKeyboardButton(name, callback_data=f"set_chat_mode|{chat_mode_key}")])
#
#     # pagination
#     if len(chat_mode_keys) > n_chat_modes_per_page:
#         is_first_page = (page_index == 0)
#         is_last_page = ((page_index + 1) * n_chat_modes_per_page >= len(chat_mode_keys))
#
#         if is_first_page:
#             keyboard.append([
#                 InlineKeyboardButton("»", callback_data=f"show_chat_modes|{page_index + 1}")
#             ])
#         elif is_last_page:
#             keyboard.append([
#                 InlineKeyboardButton("«", callback_data=f"show_chat_modes|{page_index - 1}"),
#             ])
#         else:
#             keyboard.append([
#                 InlineKeyboardButton("«", callback_data=f"show_chat_modes|{page_index - 1}"),
#                 InlineKeyboardButton("»", callback_data=f"show_chat_modes|{page_index + 1}")
#             ])
#
#     reply_markup = InlineKeyboardMarkup(keyboard)
#
#     return text, reply_markup

# async def show_chat_modes_handle(update: Update, context: CallbackContext):
#     # await register_user_if_not_exists(update, context, update.message.from_user)
#     # if await is_previous_message_not_answered_yet(update, context): return
#
#     user_id = update.message.from_user.id
#     # db.set_user_attribute(user_id, "last_interaction", datetime.now())
#
#     text, reply_markup = get_chat_mode_menu(0)
#     await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


@dataclasses.dataclass
class BotOptions:
    persona: str
    token: str
    persona_name: str


def run_bot() -> None:
    application = (
        ApplicationBuilder()
        .token(settings.AI_TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .rate_limiter(AIORateLimiter(max_retries=5))
        .http_version("1.1")
        .get_updates_http_version("1.1")
        .post_init(post_init)
        .build()
    )

    # add handlers
    user_filter = filters.ALL
    if len(settings.ALLOWED_TELEGRAM_USERNAMES) > 0:
        usernames = [
            x for x in settings.ALLOWED_TELEGRAM_USERNAMES if isinstance(x, str)
        ]
        any_ids = [x for x in settings.ALLOWED_TELEGRAM_USERNAMES if isinstance(x, int)]
        user_ids = [x for x in any_ids if x > 0]
        group_ids = [x for x in any_ids if x < 0]
        user_filter = (
            filters.User(username=usernames)
            | filters.User(user_id=user_ids)
            | filters.Chat(chat_id=group_ids)
        )

    application.add_handler(CommandHandler("start", start_handle))
    # application.add_handler(CommandHandler("help", help_handle, filters=user_filter))
    # application.add_handler(CommandHandler("help_group_chat", help_group_chat_handle, filters=user_filter))

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, message_handle)
    )
    # application.add_handler(CommandHandler("retry", retry_handle, filters=user_filter))
    # application.add_handler(CommandHandler("new", new_dialog_handle, filters=user_filter))
    # application.add_handler(CommandHandler("cancel", cancel_handle, filters=user_filter))
    #
    # application.add_handler(MessageHandler(filters.VOICE & user_filter, voice_message_handle))
    #
    # application.add_handler(CommandHandler("mode", show_chat_modes_handle, filters=user_filter))
    # application.add_handler(CallbackQueryHandler(show_chat_modes_callback_handle, pattern="^show_chat_modes"))
    # application.add_handler(CallbackQueryHandler(set_chat_mode_handle, pattern="^set_chat_mode"))
    #
    # application.add_handler(CommandHandler("settings", settings_handle, filters=user_filter))
    # application.add_handler(CallbackQueryHandler(set_settings_handle, pattern="^set_settings"))

    # This is not yet supported by us for our models
    # application.add_handler(CommandHandler("balance", show_balance_handle, filters=user_filter))

    application.add_error_handler(error_handle)

    # start the bot
    print("Starting application polling now")
    application.run_polling()


class Command(BaseCommand):
    help = (
        "Runs the practice flow test and sends status/error msg on a telegram channel"
    )

    def add_arguments(self, parser):
        pass
        # parser.add_argument("poll_ids", nargs="+", type=int)

    def handle(self, *args, **options):
        run_bot()
