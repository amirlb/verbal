FROM python:3.12-slim

WORKDIR /verbal
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src .

EXPOSE 8000
ENTRYPOINT ["streamlit", "run", "/verbal/app.py", "--server.port=8000", "--server.address=0.0.0.0"]
