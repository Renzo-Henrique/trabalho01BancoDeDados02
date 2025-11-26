ENDPOINT="http://localhost:8000"

TABLES=$(aws dynamodb list-tables --endpoint-url $ENDPOINT --query "TableNames[]" --output text)

for TABLE in $TABLES; do
    # echo " - Deletando $TABLE"
    aws dynamodb delete-table --table-name "$TABLE" --endpoint-url $ENDPOINT
done

sleep 2 # dar um tempo para o DynamoDB remover as tabelas
