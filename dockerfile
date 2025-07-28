# Usa uma imagem base Python otimizada para aplicações web
FROM python:3.11-slim-buster

# Define o diretório de trabalho dentro do contêiner
WORKDIR /app

# Copia o arquivo de requisitos e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código da aplicação
COPY . .

# Expõe a porta que a aplicação FastAPI irá escutar
# O Cloud Run requer que a aplicação escute na porta definida pela variável de ambiente PORT (padrão 8080)
ENV PORT 8080

# Comando para iniciar a aplicação usando Uvicorn
# 'main:app' refere-se ao objeto FastAPI 'app' dentro do arquivo 'main.py'
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
