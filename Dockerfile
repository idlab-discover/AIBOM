# Use Python 3.10 for ml-metadata compatibility
FROM python:3.10-slim

WORKDIR /app
COPY app /app
COPY requirements.txt /app/

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

CMD ["python", "main.py"]
