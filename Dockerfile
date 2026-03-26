FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY . /app

RUN mkdir -p /tmp/uploads

EXPOSE 8080

CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 300 --keep-alive 75