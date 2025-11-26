#!/bin/bash
set -e

ENDPOINT="http://localhost:8000"
DATA_DIR="/home/dynamodblocal/init/data"
BATCH_SIZE=25

echo "===== Inserindo itens em batches de $BATCH_SIZE ==="

# Itera sobre todos os arquivos .json do diretório
for ITEMS_FILE in "$DATA_DIR"/*.json; do
    echo "Processando arquivo: $ITEMS_FILE"

    # Itera sobre cada tabela dentro do JSON
    for TABLE_NAME in $(jq -r 'keys[]' "$ITEMS_FILE"); do
        TOTAL_ITEMS=$(jq ".\"$TABLE_NAME\" | length" "$ITEMS_FILE")
        echo "Tabela $TABLE_NAME: $TOTAL_ITEMS itens"

        for ((i=0; i<$TOTAL_ITEMS; i+=BATCH_SIZE)); do
            # Cria batch de até 25 itens
            jq ".\"$TABLE_NAME\"[$i:$((i+BATCH_SIZE))] | {\"$TABLE_NAME\": .}" "$ITEMS_FILE" > /tmp/batch.json

            # Envia batch para DynamoDB Local
            aws dynamodb batch-write-item --request-items file:///tmp/batch.json --endpoint-url $ENDPOINT

            echo "Batch $((i/BATCH_SIZE+1)) enviado para $TABLE_NAME"
        done
    done
done

echo "===== Todos os itens foram inseridos ==="
