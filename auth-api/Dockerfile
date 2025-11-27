FROM python:3.10-slim

WORKDIR /app

# Instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY main.py .

# Comando de execução da API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]