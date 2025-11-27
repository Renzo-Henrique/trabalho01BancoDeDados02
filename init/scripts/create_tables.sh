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

    # Verifica se a tabela já existe
    if aws dynamodb describe-table --table-name "$TABLE_NAME" --endpoint-url $ENDPOINT &> /dev/null; then
        # echo "	Tabela $TABLE_NAME já existe, pulando..."
		:
    else
        #echo "Criando tabela $TABLE_NAME..."
        aws dynamodb create-table \
            --cli-input-json "$row" \
            --endpoint-url $ENDPOINT
        #echo "	Tabela $TABLE_NAME criada!"
		# Se uma tabela foi criada, define a flag como 1
        INIT_FLAG=1
    fi
done

# Pequeno delay para garantir que a tabela esteja ativa
sleep 2

# === LÓGICA DE INICIALIZAÇÃO CONDICIONAL ===
if [[ "$INIT_FLAG" == "1" ]]; then
    echo "===== Inserindo dados iniciais... ====="
    # Chama o init_tables.sh diretamente
    bash "$INIT_SCRIPT"
else
    echo "===== Nenhuma tabela nova criada."
	echo "===== Mantendo dados existentes. "
fi