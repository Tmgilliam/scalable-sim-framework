FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default entrypoint for Vertex AI Custom Job
# Vertex will pass --bucket / --prefix / --scenarios / --seeds as args
ENTRYPOINT ["python", "-c", "from cloud.vertex_job import _entrypoint; _entrypoint()"]
