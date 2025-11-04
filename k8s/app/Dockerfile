FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy application source from build context (./app)
COPY . /app/

RUN useradd -u 1000 -m appuser && chown -R 1000 /app
USER 1000

CMD ["python", "main.py"]
