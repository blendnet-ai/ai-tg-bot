# syntax=docker/dockerfile:experimental
FROM python:3.11-slim

# Standard recommendation for Python Docker Images
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MAKEFLAGS=-j2

# Create the user
# Ref: https://code.visualstudio.com/remote/advancedcontainers/add-nonroot-user
# We install all dependencies together as the later half of the image lacks root access
RUN apt-get update && apt-get dist-upgrade --yes && \
    apt-get install --yes build-essential python3-dev libpq-dev git openssh-client && \
    apt-get autoremove --yes && apt-get autoclean --yes && apt-get clean

ARG USERNAME=appuser
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME && \
    chown -R $USER_UID:$USER_GID /home/$USERNAME

# RUN --mount=type=ssh mkdir -m 0600 ~/.ssh && \
#     ssh-keyscan github.com >> ~/.ssh/known_hosts && \
#     pip install git+ssh://git@github.com/blendnet-ai/pip-module.git#pip-module

USER $USERNAME
ENV PATH "$PATH:/home/$USERNAME/.local/bin"

# Install dependencies
COPY --chown=$USER_UID:$USER_GID requirements.txt /home/$USERNAME/code/
WORKDIR /home/$USERNAME/code
RUN pip install safety && safety check -r requirements.txt
RUN pip install -r /home/$USERNAME/code/requirements.txt

# We want to build with closest to production environment as possible
ARG DJANGO_DEBUG=FALSE

# Dummy credentials for build only!
ENV DJANGO_SETTINGS_MODULE=ai_tg_bot.settings \
    DJANGO_DEBUG=${DJANGO_DEBUG} \
    POSTGRES_HOST=postgres \
    POSTGRES_PORT=5432 \
    POSTGRES_DB=db_name \
    POSTGRES_USER=postgres \
    POSTGRES_PASSWORD=password \
    DJANGO_SECRET=django-dummyXXX-48q8pwxm&lyupXm0x7^ar18c)r&ro45lr3zxd%%rxzzpzxa3_) \
    AI_TELEGRAM_BOT_TOKEN=token \
    ALLOWED_TELEGRAM_USERNAMES=[]

COPY  --chown=$USER_UID:$USER_GID . /home/$USERNAME/code/
# RUN python manage.py collectstatic --noinput
ENTRYPOINT gunicorn ai_tg_bot.asgi --bind=0.0.0.0:8000 --workers=2 -k uvicorn.workers.UvicornWorker --log-file=- --access-logfile=-
