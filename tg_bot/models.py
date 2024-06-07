import random
from django.db import models
from django.contrib.auth.models import User

from django.contrib.auth import get_user_model


def generate_random_number():
    # Generates a random number between 100000 and 999999
    return random.randint(100000, 999999)


class AgentConfig(models.Model):
    persona_text = models.TextField(max_length=1000)
    llm_config = models.JSONField(default=dict)
    name = models.CharField(max_length=20)
    memgpt_preset_name = models.CharField(max_length=25, default="custom_preset")


class UserProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, to_field="id")
    otp = models.IntegerField(default=generate_random_number)

    def get_user_details_for_memgpt(self) -> str:
        return ""


class Agent(models.Model):
    """
    Memgpt Agent instance
    """

    user = models.ForeignKey(to=get_user_model(), on_delete=models.CASCADE)
    telegram_chat_id = models.CharField(max_length=20, null=False, unique=True)
    memgpt_agent_id = models.UUIDField(null=True)
    config = models.ForeignKey(AgentConfig, null=False, on_delete=models.CASCADE)
    user_profile = models.ForeignKey(UserProfile, null=False, on_delete=models.CASCADE)
