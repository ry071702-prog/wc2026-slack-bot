# HF Spaces (Docker) 用。ビルドコンテキストは Space リポジトリのルート
# (bolt_app/ と src/ を同梱した構成でアップロードする)
FROM python:3.12-slim

WORKDIR /app

COPY bolt_app/requirements.txt /app/bolt_app/requirements.txt
RUN pip install --no-cache-dir -r /app/bolt_app/requirements.txt

COPY src /app/src
COPY bolt_app /app/bolt_app

ENV PYTHONUNBUFFERED=1
EXPOSE 7860

CMD ["python", "bolt_app/app.py"]
