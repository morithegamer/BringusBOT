# Use official Python base
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Copy requirement file and install dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your bot code
COPY . .

# Final command is handled by docker-compose