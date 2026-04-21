FROM python:3.13-slim

WORKDIR /app

# System deps for gcloud CLI (needed for ADC token refresh)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
       > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
       | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y --no-install-recommends google-cloud-cli \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code (data/ excluded via .dockerignore — mounted as volume)
COPY . .

EXPOSE 8200

CMD ["python", "dashboard.py"]
