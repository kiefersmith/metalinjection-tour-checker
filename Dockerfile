FROM python:3.12-slim

WORKDIR /app

COPY *.py /app
COPY requirements.txt /app
COPY start.sh /app

RUN pip3 install -r requirements.txt

RUN python -m playwright install-deps firefox && \
    python -m playwright install firefox

EXPOSE 5000

CMD [ "sh", "start.sh" ]
