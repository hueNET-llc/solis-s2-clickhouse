FROM python:3.12-alpine

COPY . /solis-s2

WORKDIR /solis-s2

RUN pip install -r requirements.txt

ENTRYPOINT ["python", "-u", "solis-s2.py"]