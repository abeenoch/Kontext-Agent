FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN apt-get update && apt-get install -y libglib2.0-0 libsm6 libxrender1 libxext6
RUN pip install --no-cache-dir --upgrade pip && pip install -r requirements.txt
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
