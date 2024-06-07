from datetime import datetime
import logging
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from tg_bot.models import Agent, AgentConfig, UserProfile
from tg_bot.memgpt_wrapper import MemGPTWrapper

from asgiref.sync import sync_to_async

gpt_wrapper = MemGPTWrapper()
logger = logging.getLogger(__name__)


def get_now() -> datetime:
    required_timezone = "Asia/Kolkata"
    return datetime.now(ZoneInfo(required_timezone))


def split_text_into_chunks(text, chunk_size):
    for i in range(0, len(text), chunk_size):
        yield text[i : i + chunk_size]


async def is_bot_mentioned(update: Update, context: CallbackContext):
    message = update.message
    if message.chat.type == "private":
        return True
    if message.text and ("@" + context.bot.username) in message.text:
        return True
    if (
        message.reply_to_message
        and message.reply_to_message.from_user.id == context.bot.id
    ):
        return True
    return False


@sync_to_async
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
                f"Agent config -<{agent_config_name}> doesn't exist. \n"
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
                agent_id = gpt_wrapper.create_agent(agent_config_name, user_profile)
                agent = Agent.objects.create(
                    user=user_profile.user,
                    telegram_chat_id=chat_id,
                    memgpt_agent_id=agent_id,
                    config=agent_config,
                    user_profile=user_profile,
                )
                agent.save()
            else:
                return None, "Wrong OTP."
    return gpt_wrapper.get_agent_config(agent.memgpt_agent_id), ""


@sync_to_async
def delete_agent(message_text: str, chat_id: int):
    try:
        otp = int(message_text.split(",")[1])
        UserProfile.objects.get(otp=otp)
    except UserProfile.DoesNotExist:
        return False, "Wrong OTP."
    except Exception as e:
        return None, f"Error while parsing msg - {e}"
    else:
        agent = Agent.objects.get(telegram_chat_id=chat_id)
        gpt_wrapper.delete_agent(agent.memgpt_agent_id)
        agent.delete()
        return True, ""


@sync_to_async
def reset_agent_persona(chat_id: int):
    agent = Agent.objects.get(telegram_chat_id=chat_id)
    gpt_wrapper.delete_agent(agent.memgpt_agent_id)
    agent_id = gpt_wrapper.create_agent(agent.config.name, agent.user_profile)
    agent.memgpt_agent_id = agent_id
    agent.save()
