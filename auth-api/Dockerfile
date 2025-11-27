FROM python:3.10-slim

WORKDIR /app

# Instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y curl

# Copia o código da aplicação
COPY main.py .
COPY test_auth.py .

# Comando de execução da API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]