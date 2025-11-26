FROM amazon/dynamodb-local:latest

USER root

# Instala unzip, curl, jq
RUN yum install -y unzip jq

# Instala AWS CLI
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf awscliv2.zip aws

# Copia init para dentro do container
COPY init /home/dynamodblocal/init
RUN chmod +x /home/dynamodblocal/init/scripts/entrypoint.sh
RUN chmod +x /home/dynamodblocal/init/scripts/create_tables.sh
RUN chmod +x /home/dynamodblocal/init/scripts/init_tables.sh
RUN chmod +x /home/dynamodblocal/init/scripts/clean_db.sh

ENTRYPOINT ["sh", "./init/scripts/entrypoint.sh"]

WORKDIR /home/dynamodblocal