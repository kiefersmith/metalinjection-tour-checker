FROM python:3.9-alpine

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY main.py .

RUN mkdir articles

CMD [ "python", "main.py" ]
