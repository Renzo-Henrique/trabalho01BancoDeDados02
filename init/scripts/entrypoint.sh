#!/bin/bash
set -e

# Inicia o DynamoDB em background
java -jar DynamoDBLocal.jar -sharedDb -dbPath ./data &

# Espera alguns segundos para o DynamoDB iniciar
echo "Aguardando o DynamoDB iniciar..."
sleep 5

if [[ "$RESET_DB" == "true" ]]; then
	echo "=== RESET_DB=true :: Limpando todas as tabelas ==="
	bash /home/dynamodblocal/init/scripts/clean_db.sh
else
	echo "=== RESET_DB=false :: Mantendo tabelas existentes ==="
fi

# Executa script de criação de tabelas
bash /home/dynamodblocal/init/scripts/create_tables.sh

# Insere dados
bash /home/dynamodblocal/init/scripts/init_tables.sh

# Mantém o processo principal em foreground
wait
