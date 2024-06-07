# Generated by Django 4.2.11 on 2024-06-07 12:44

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import tg_bot.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('persona_text', models.TextField(max_length=1000)),
                ('llm_config', models.JSONField(default=dict)),
                ('name', models.CharField(max_length=20)),
                ('memgpt_preset_name', models.CharField(default='custom_preset', max_length=25)),
            ],
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('otp', models.IntegerField(default=tg_bot.models.generate_random_number)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Agent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('telegram_chat_id', models.CharField(max_length=20, unique=True)),
                ('memgpt_agent_id', models.UUIDField(null=True)),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tg_bot.agentconfig')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('user_profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tg_bot.userprofile')),
            ],
        ),
    ]
