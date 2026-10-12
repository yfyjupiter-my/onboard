FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl gettext \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh \
    && DJANGO_SECRET_KEY=build DATABASE_URL=sqlite:// MINIO_ENDPOINT=http://x MINIO_ROOT_USER=x MINIO_ROOT_PASSWORD=x \
       python manage.py compilemessages --ignore=.venv  # T7.2: .po -> .mo baked into the image

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
