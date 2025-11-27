#!/bin/bash
set -e

# Scripts
CREATE_TABLE_SCRIPT="/home/dynamodblocal/init/scripts/create_tables.sh"
CLEAN_TABLE_SCRIPT="/home/dynamodblocal/init/scripts/clean_db.sh"

# Inicia o DynamoDB em background
java -jar DynamoDBLocal.jar -sharedDb -dbPath ./data &

# Espera alguns segundos para o DynamoDB iniciar
echo "Aguardando o DynamoDB iniciar..."
sleep 5

if [[ "$RESET_DB" == "true" ]]; then
	echo "=== RESET_DB=true :: Limpando todas as tabelas ==="
	bash $CLEAN_TABLE_SCRIPT
else
	echo "=== RESET_DB=false :: Mantendo tabelas existentes ==="
fi

# Executa script de criação de tabelas
bash $CREATE_TABLE_SCRIPT

echo " "
echo "Inicializacao finalizada!"
# Mantém o processo principal em foreground
wait
