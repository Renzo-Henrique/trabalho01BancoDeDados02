#!/bin/bash
set -e

# Inicia o DynamoDB em background
java -jar DynamoDBLocal.jar -sharedDb -dbPath ./data &

# Espera alguns segundos para o DynamoDB iniciar
echo "Aguardando o DynamoDB iniciar..."
sleep 5

# Executa script de criação de tabelas
bash /home/dynamodblocal/init/scripts/create_tables.sh

# Insere dados
bash /home/dynamodblocal/init/scripts/init_tables.sh

# Mantém o processo principal em foreground
wait
