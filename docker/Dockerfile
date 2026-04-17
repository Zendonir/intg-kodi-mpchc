FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY driver.json .

RUN useradd -m -u 1000 ucremote && chown -R ucremote:ucremote /app
USER ucremote

EXPOSE 9090

CMD ["python", "src/driver.py"]
