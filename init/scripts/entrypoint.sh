#!/bin/bash
set -e

# Scripts
CREATE_TABLE_SCRIPT="/home/dynamodblocal/init/scripts/create_tables.sh"
CLEAN_TABLE_SCRIPT="/home/dynamodblocal/init/scripts/clean_db.sh"
DB_DIR="/home/dynamodblocal/data"
DB_FILE="$DB_DIR/shared-local-instance.db"


# Inicia o DynamoDB em background
java -jar DynamoDBLocal.jar -sharedDb -dbPath ./data &

# Espera alguns segundos para o DynamoDB iniciar
echo "Aguardando o DynamoDB iniciar..."
sleep 3


if [ -d "$DB_DIR" ] && [ -f "$DB_FILE" ]; then
    echo "Banco de dados já inicializado. Pulando inicialização"

else
	bash $CREATE_TABLE_SCRIPT
fi


echo " "
echo "Inicializado. Leia o README para mais orientações!"
# Mantém o processo principal em foreground
wait
