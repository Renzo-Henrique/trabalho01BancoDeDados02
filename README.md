# trabalho01BancoDeDados02




# TODO::
criar arquivo separado indicando chave primária das tabelas



docker compose down
docker compose build --no-cache
docker compose up



# Remover containers
docker stop $(docker container ls -aq)
docker rm $(docker container ls -aq)
docker volume rm -f $(docker volume ls -q)
docker image prune -a -f





## TODO::
 - Colocar que balance é obrigatório com validadores ou scripts