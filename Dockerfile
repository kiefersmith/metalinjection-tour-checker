FROM python:3.9-alpine

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY *.py .

# Overwritten by the mounted volume at runtime; present so local runs work too.
RUN mkdir articles

CMD [ "python", "main.py" ]
