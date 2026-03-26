# Use slim Python base instead of full image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install only system deps needed
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python deps — no cache to save space
RUN pip install --no-cache-dir -r requirements.txt

# Copy only necessary app files
COPY app.py .
COPY env.py .
COPY data_loader.py .
COPY dqn.py .
COPY qlearning.py .
COPY Procfile .
COPY static/ ./static/
COPY templates/ ./templates/

# Don't copy these (they're huge and not needed):
# *.pkl, *.pt, *.npy, *.zip, venv/, ai-adaptive-firewall/

EXPOSE 8080

CMD ["python", "app.py"]
