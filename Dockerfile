FROM python:3.11-slim

# Install requests
RUN pip install --no-cache-dir requests

# Copy the ddns script
COPY cf-ddns.py /app/cf-ddns.py

WORKDIR /app

# Run the script
CMD ["python", "cf-ddns.py"]
