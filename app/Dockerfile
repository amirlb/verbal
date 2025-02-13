FROM python:3.12-slim

WORKDIR /verbal
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py .
COPY .streamlit .streamlit
COPY verbal verbal

ENTRYPOINT ["streamlit", "run", "main.py"]
