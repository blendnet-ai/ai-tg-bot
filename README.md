## Setup using Docker

1. Install Docker Desktop and latest docker-cli and confirm that "docker compose" command works.
   Checkout the repo.
2. You might need to do "export GH_TOKEN=<your_classic_github_token>;docker login ghcr.io" before running "docker compose" if it shows an auth error. Here github classic token needs to be created via Github Dashboard.
3. Copy the .env and memgpt_config folder file provided to you in the root directory.

Setting Up first time Postgres

```
⁠docker volume create bot-pgdb
docker compose up bot-postgres
```

Run development server

```
docker compose up bot-dev
```

Run initial migrations

```
docker compose up bot-dbmigrate
```

## Testing

1. Create an entry in `auth_user` table
2. Create an entry in `tg_bot_userprofile` using the id of previously created user
3. Creat and entry in `tg_bot_agentconfig` table. The following json can be used for `llm_config` field:

```
{
  "model": "gpt-4",
  "model_wrapper": null,
  "context_window": 8192,
  "model_endpoint": "https://api.openai.com/v1",
  "model_endpoint_type": "openai"
}
```

4. Search the bot on Telegram and start interacting

## Persona reset flow

1. Update the `persona_text` in `tg_bot_agentconfig`
2. Send `/reset_persona` on Telegram chat
