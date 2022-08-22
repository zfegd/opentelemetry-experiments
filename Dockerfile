FROM tiangolo/uvicorn-gunicorn-fastapi:python3.8 as base
COPY ./requirements.txt /requirements.txt
RUN pip install -r /requirements.txt
COPY ./app /app
ENV PYTHONPATH /app
