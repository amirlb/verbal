FROM python:3.12-slim

WORKDIR /verbal
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

ENV OPENAI_API_KEY=
ENV OPENAI_MODEL=gpt-4o-mini

EXPOSE 8501
ENTRYPOINT ["streamlit", "run", "src/app.py", "--server.address=0.0.0.0"]
