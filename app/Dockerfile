FROM python:3.12-slim

WORKDIR /tmp
COPY requirements.txt .
RUN pip install -r requirements.txt

WORKDIR /verbal

ENTRYPOINT ["streamlit", "run", "/verbal/app/src/app.py"]
