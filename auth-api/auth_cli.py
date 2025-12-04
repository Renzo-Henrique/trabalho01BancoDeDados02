import sys
import os
import re
from getpass import getpass
from typing import List, Dict, Any, Tuple

# 1. Configuração e Dependências
try:
    import boto3
    from botocore.exceptions import ClientError
    from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
except ImportError:
    print("Erro: As bibliotecas Boto3 e botocore são necessárias. Certifique-se de que estão no requirements.txt.")
    sys.exit(1)

# 2. Inicialização do Cliente DynamoDB
# Assume que as variáveis de ambiente (DYNAMODB_ENDPOINT, AWS_REGION) estão configuradas no docker-compose.yml
try:
    dynamodb_client = boto3.client(
        'dynamodb',
        region_name=os.environ.get("AWS_REGION", "us-west-2"),
        endpoint_url=os.environ.get("DYNAMODB_ENDPOINT", "http://dynamodb-local:8000")
    )
    # Ferramentas para converter formatos do DynamoDB (M, L, S, N) para Python nativo
    deserializer = TypeDeserializer()
    serializer = TypeSerializer()
except Exception as e:
    print(f"Erro ao inicializar o cliente DynamoDB: {e}")
    sys.exit(1)

# --- Funções de Utilitários e Core ---

def deserialize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Converte um item do formato DynamoDB (com tipos 'S', 'N', 'L', etc.) para um dicionário Python nativo."""
    return {k: deserializer.deserialize(v) for k, v in item.items()}

def serialize_item(data: Dict[str, Any]) -> Dict[str, Any]:
    """Converte um dicionário Python nativo para o formato DynamoDB (para uso em put/update/delete com a API padrão)"""
    return {k: serializer.serialize(v) for k, v in data.items()}

def validar_usuario_cli(username: str, password: str) -> List[str] | None:
    """Valida o usuário e retorna a lista de nomes de papéis (role_names)."""
    try:
        # 1. Obter usuário da tabela 'users'
        response = dynamodb_client.get_item(
            TableName='users',
            Key={'username': {'S': username}},
            ConsistentRead=True # Garante que a leitura seja consistente
        )
        user_item = response.get('Item')
        if not user_item:
            return None 

        # 2. Deserializar item e verificar senha
        user_data = deserialize_item(user_item)
        
        # NOTA: Em um sistema real, aqui você usaria 'bcrypt.checkpw' ou similar.
        # Estamos usando comparação de texto simples, pois o 'users_batch.json' armazena a senha em texto simples.
        if user_data.get('password') != password:
            return None

        # 3. Retorna a lista de roles (garante que seja uma lista, mesmo que o JSON armazene como 'L')
        role_names = user_data.get('role_name', [])
        if not isinstance(role_names, list):
            role_names = [role_names] # Caso seja apenas uma string
        return role_names

    except ClientError as e:
        print(f"Erro no DynamoDB durante a autenticação: {e.response['Error']['Message']}")
        return None
    except Exception as e:
        print(f"Erro inesperado na autenticação: {e}")
        return None


def get_permissions_for_roles(role_names: List[str]) -> List[str]:
    """Busca a lista completa de permissões dado os nomes dos papéis."""
    all_permissions = set()
    try:
        for role_name in role_names:
            response = dynamodb_client.get_item(
                TableName='roles',
                Key={'role_name': {'S': role_name}},
                ConsistentRead=True
            )
            role_item = response.get('Item')
            if role_item:
                role_data = deserialize_item(role_item)
                permissions_list = role_data.get('permissions', [])
                all_permissions.update(permissions_list)
    except ClientError as e:
        print(f"Erro ao buscar permissões: {e.response['Error']['Message']}")
    return list(all_permissions)

def analisar_partiql(query: str) -> Tuple[str, str] | None:
    """
    Extrai a ação (read/write/update/delete) e o nome da tabela da consulta PartiQL.
    Simplifica a análise de strings para cobrir os comandos principais.
    """
    query_upper = query.strip().upper()
    tokens = re.split(r'\s+', query_upper)
    
    if not tokens:
        return None

    action_token = tokens[0]
    
    # Padroniza a obtenção do nome da tabela (que é o token seguinte à palavra-chave)
    table_name = None
    
    if action_token == "SELECT":
        # SELECT ... FROM tabela
        try:
            from_index = tokens.index('FROM')
            # O nome da tabela pode estar entre aspas duplas, removemos
            table_name = tokens[from_index + 1].strip('"').strip("'").lower()
            return 'read', table_name
        except ValueError:
            print("Erro de sintaxe PartiQL: 'FROM' não encontrado em SELECT.")
            return None
    
    elif action_token == "INSERT":
        # INSERT INTO tabela ...
        try:
            into_index = tokens.index('INTO')
            table_name = tokens[into_index + 1].strip('"').strip("'")
            return 'write', table_name
        except ValueError:
            print("Erro de sintaxe PartiQL: 'INTO' não encontrado em INSERT.")
            return None
            
    elif action_token == "UPDATE":
        # UPDATE tabela ... (tabela é o segundo token)
        try:
            table_name = tokens[1].strip('"').strip("'")
            return 'update', table_name
        except IndexError:
            print("Erro de sintaxe PartiQL: Nome da tabela faltando após UPDATE.")
            return None

    elif action_token == "DELETE":
        # DELETE FROM tabela ...
        try:
            from_index = tokens.index('FROM')
            table_name = tokens[from_index + 1].strip('"').strip("'")
            return 'delete', table_name
        except ValueError:
            print("Erro de sintaxe PartiQL: 'FROM' não encontrado em DELETE.")
            return None
    
    print(f"Ação PartiQL não reconhecida ou não suportada para autorização: {action_token}")
    return None

def verificar_permissao_cli(permissions: List[str], table: str, action: str) -> bool:
    """Verifica se as permissões concedidas permitem a ação na tabela (RBAC)."""
    required_permission = f"{table.lower()}:{action}"
    
    # 1. Permissão total (admin)
    if '*' in permissions:
        return True
        
    # 2. Permissão específica: 'tabela:ação' (ex: 'customer:read')
    if required_permission in permissions:
        return True

    # 3. Permissão curinga da tabela: 'tabela:*'
    table_wildcard = f"{table}:*"
    if table_wildcard in permissions:
        return True

    return False


def executar_partiql(query: str) -> Dict[str, Any] | None:
    """Executa a consulta PartiQL no DynamoDB e trata a resposta/erros."""
    try:
        response = dynamodb_client.execute_statement(Statement=query)
        return response
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"❌ ERRO DO DYNAMODB ({error_code}): {error_message}")
        return None
    except Exception as e:
        print(f"❌ ERRO INESPERADO NA EXECUÇÃO DE PARTIQL: {e}")
        return None


def main():
    """Lógica principal do cliente CLI: login, loop de consultas e autorização."""
    print("🛡️ Cliente PartiQL Autorizado para DynamoDB Local (RBAC) 🛡️")
    username = input("Usuário: ")
    password = getpass("Senha: ")
    
    # 1. Autenticação
    role_names = validar_usuario_cli(username, password)
    if not role_names:
        print("\n❌ Autenticação falhou: Usuário ou senha inválidos.")
        sys.exit(1)

    # 2. Obter Permissões
    permissions = get_permissions_for_roles(role_names)
    print(f"\n✅ Autenticado como **{username}** com papéis: {', '.join(role_names)}")
    print("   Digite 'exit', 'quit' ou pressione Ctrl+D para sair.")
    
    # 3. Loop Interativo
    while True:
        try:
            # Mostra o nome do usuário e o primeiro papel no prompt
            prompt_role = role_names[0] if role_names else 'unknown'
            query = input(f"{username}@{prompt_role} $ ")
        except EOFError:
            break # Ctrl+D
            
        if query.strip().lower() in ['exit', 'quit']:
            break
        
        if not query.strip():
            continue
            
        # 4. Autorização
        parse_result = analisar_partiql(query)
        if not parse_result:
            continue
            
        action, table_name = parse_result
        
        if verificar_permissao_cli(permissions, table_name, action):
            print(f"   [Autorizado] Permissão '{table_name}:{action}' concedida. Executando...")
            
            # 5. Execução
            result = executar_partiql(query)
            
            # 6. Exibição do Resultado
            if result:
                if 'Items' in result:
                    print("\n--- Resultados (Deserializados) ---")
                    # Deserializa a lista de itens para uma visualização mais amigável
                    deserialized_items = [deserialize_item(item) for item in result['Items']]
                    for item in deserialized_items:
                        print(item)
                    print("----------------------------------\n")
                elif result.get('UpdateSummary'):
                    print("\n✅ Operação de escrita/atualização concluída com sucesso.\n")
                else:
                    # Para operações como INSERT/UPDATE/DELETE que não retornam 'Items'
                    print("\n✅ Comando executado com sucesso (sem itens de retorno).\n")


        else:
            print(f"\n❌ ERRO DE AUTORIZAÇÃO: O usuário '{username}' (papel: {prompt_role}) não tem a permissão **'{table_name}:{action}'** necessária.")
            print("----------------------------------\n")


    print("\nSaindo do cliente PartiQL.")

if __name__ == "__main__":
    main()