#!/bin/bash
set -e

# Caminho para o JSON de tabelas
TABLES_FILE="/home/dynamodblocal/init/schema/tables.json"

# Endpoint do DynamoDB Local
ENDPOINT="http://localhost:8000"

echo "===== Iniciando criação de tabelas..."

for row in $(jq -c '.[]' $TABLES_FILE); do
    TABLE_NAME=$(echo $row | jq -r '.TableName')

    # Verifica se a tabela já existe
    if aws dynamodb describe-table --table-name "$TABLE_NAME" --endpoint-url $ENDPOINT &> /dev/null; then
        echo "Tabela $TABLE_NAME já existe, pulando..."
    else
        echo "Criando tabela $TABLE_NAME..."
        aws dynamodb create-table \
            --cli-input-json "$row" \
            --endpoint-url $ENDPOINT
        echo "Tabela $TABLE_NAME criada!"
    fi
done

# Pequeno delay para garantir que a tabela esteja ativa
sleep 2

echo "Todas as tabelas foram processadas."
