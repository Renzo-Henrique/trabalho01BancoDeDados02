#!/bin/bash
set -e

# Caminho para o JSON de tabelas
TABLES_FILE="/home/dynamodblocal/init/schema/tables.json"
# Script de inicialização de dados
INIT_SCRIPT="/home/dynamodblocal/init/scripts/init_tables.sh"
# Endpoint do DynamoDB Local
ENDPOINT="http://localhost:8000"

echo "===== Iniciando criação de tabelas..."
# Inicializa a variável (0 = Nenhuma tabela criada)
INIT_FLAG=0

for row in $(jq -c '.[]' $TABLES_FILE); do
    TABLE_NAME=$(echo $row | jq -r '.TableName')

    #echo "Criando tabela $TABLE_NAME..."
    aws dynamodb create-table \
        --cli-input-json "$row" \
        --endpoint-url $ENDPOINT
    echo "Tabela $TABLE_NAME criada!"
done

# Pequeno delay para garantir que as tabelas estejam ativas
sleep 2