import sys
import os
import re
import json
from getpass import getpass
from typing import List, Dict, Any, Tuple, Optional
import shlex

# 1. Configuração e Dependências
try:
    import boto3
    from botocore.exceptions import ClientError
    from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
except ImportError:
    print("Erro: As bibliotecas Boto3 e botocore são necessárias. Certifique-se de que estão no requirements.txt.")
    sys.exit(1)

# 2. Inicialização do Cliente DynamoDB
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

# --- Funções de Utilitários e Core (Mantidas) ---

def deserialize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Converte um item do formato DynamoDB (com tipos 'S', 'N', 'L', etc.) para um dicionário Python nativo."""
    # Trata o caso de Item vazio (ocorre em DELETE, por exemplo)
    if not item:
        return {}
    return {k: deserializer.deserialize(v) for k, v in item.items()}

def serialize_item(data: Dict[str, Any]) -> Dict[str, Any]:
    """Converte um dicionário Python nativo para o formato DynamoDB (para uso em put/update/delete com a API padrão)"""
    return {k: serializer.serialize(v) for k, v in data.items()}

# --- Funções de Autenticação e Autorização (Mantidas) ---

def validar_usuario_cli(username: str, password: str) -> List[str] | None:
    """Valida o usuário e retorna a lista de nomes de papéis (role_names)."""
    try:
        response = dynamodb_client.get_item(
            TableName='users',
            Key={'username': {'S': username}},
            ConsistentRead=True
        )
        user_item = response.get('Item')
        if not user_item: return None 
        user_data = deserialize_item(user_item)
        
        if user_data.get('password') != password:
            return None

        role_names = user_data.get('role_name', [])
        if not isinstance(role_names, list):
            role_names = [role_names]
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

def to_camel_case(snake_str: str) -> str:
    """Converte snake_case para CamelCase (seguindo a convenção do Boto3)"""
    components = snake_str.split('_')
    # Capitaliza todas as partes, exceto a primeira letra do primeiro componente
    # e junta. Ex: 'table_name' -> 'TableName'
    return components[0].capitalize() + ''.join(x.capitalize() for x in components[1:])
    # Nota: Em Boto3, a primeira letra é maiúscula (TableName, Key), diferentemente do Python padrão.
    # Ex: 'table_name' -> 'TableName', 'key' -> 'Key'

def verificar_permissao_cli(permissions: List[str], table: str, action: str) -> bool:
    """Verifica se as permissões concedidas permitem a ação na tabela (RBAC)."""
    required_permission = f"{table.lower()}:{action}"
    
    if '*' in permissions: return True
    if required_permission in permissions: return True
    
    table_wildcard = f"{table}:*"
    if table_wildcard in permissions: return True

    return False

# --- NOVAS FUNÇÕES: Parser e Executor do Comando AWS CLI (Simulado) ---

# Mapeamento para traduzir comandos AWS CLI em ações RBAC
AWS_CLI_ACTION_MAP = {
    "get-item": "read",
    "query": "read",
    "scan": "read",
    "put-item": "write",
    "update-item": "update",
    "delete-item": "delete",
    "batch-get-item": "read",
    "batch-write-item": "write",
}

def split_cli_command(command: str) -> List[str]:
    """Divide o comando em tokens de forma correta usando shlex."""
    try:
        return shlex.split(command)
    except ValueError:
        print("Erro ao analisar o comando: verifique aspas e sintaxe.")
        return []

def analisar_aws_cli_comando(command: str) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """
    Extrai a ação (read/write/update/delete) e a tabela do comando AWS CLI simulado.
    Retorna (ação, tabela, argumentos_para_execucao)
    """
    command_tokens = split_cli_command(command.strip())

    if len(command_tokens) < 3 or command_tokens[0].lower() != 'dynamodb':
        print("Erro: O comando deve começar com 'dynamodb <ACAO>'.")
        return None

    cli_action = command_tokens[1].lower()
    
    # 1. Mapeamento da Ação RBAC
    rbac_action = AWS_CLI_ACTION_MAP.get(cli_action)
    if not rbac_action:
        print(f"Ação AWS CLI não reconhecida ou não suportada para autorização: {cli_action}")
        return None

    # 2. Parsing e Conversão de Argumentos
    args_dict = {}
    i = 2
    while i < len(command_tokens):
        token = command_tokens[i]
        if token.startswith('--'):
            param_name_snake = token.lstrip('--').replace('-', '_')
            # 🚨 CONVERSÃO AQUI: converte snake_case para CamelCase do Boto3
            param_name_camel = to_camel_case(param_name_snake)
            
            i += 1
            if i < len(command_tokens):
                value = command_tokens[i]
                
                # Tenta parsear JSON para argumentos complexos
                if param_name_snake in ['key', 'item', 'expression_attribute_names', 'expression_attribute_values']:
                    try:
                        args_dict[param_name_camel] = json.loads(value)
                    except json.JSONDecodeError:
                        args_dict[param_name_camel] = value
                else:
                    args_dict[param_name_camel] = value
        i += 1
        
    # 3. Extração da Tabela (usando a chave CamelCase)
    table_name = args_dict.get('TableName')
    if not table_name:
        print("Erro de sintaxe: Parâmetro '--table-name' é obrigatório.")
        return None
        
    return rbac_action, table_name.lower(), args_dict

def executar_aws_cli_comando(cli_action: str, args: Dict[str, Any]) -> Dict[str, Any] | None:
    """Executa o comando nativo do DynamoDB (boto3) usando a ação e os argumentos parseados."""
    try:
        # Pega a função correspondente no cliente boto3
        method = getattr(dynamodb_client, cli_action.replace('-', '_'))
        
        # O método execute-statement é reservado para PartiQL e não deve ser usado aqui
        # Nota: 'Args' já contém todos os parâmetros como 'TableName', 'Key', 'Item', etc.
        response = method(**args) 
        
        return response
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"❌ ERRO DO DYNAMODB ({error_code}): {error_message}")
        return None
    except AttributeError:
        print(f"❌ ERRO: O método '{cli_action}' não é um comando válido do cliente DynamoDB.")
        return None
    except Exception as e:
        print(f"❌ ERRO INESPERADO NA EXECUÇÃO DE '{cli_action}': {e}")
        return None

def main():
    """Lógica principal do cliente CLI: login, loop de comandos e autorização."""
    print("🛡️ Cliente AWS CLI Autorizado para DynamoDB Local (RBAC) 🛡️")
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
    print("   Digite comandos simulados do AWS CLI (e.g., dynamodb get-item) ou 'exit' para sair.")
    
    # 3. Loop Interativo
    while True:
        try:
            prompt_role = role_names[0] if role_names else 'unknown'
            command = input(f"{username}@{prompt_role} $ ")
        except EOFError:
            break
            
        if command.strip().lower() in ['exit', 'quit']:
            break
        
        if not command.strip():
            continue
            
        # 4. Autorização
        parse_result = analisar_aws_cli_comando(command)
        if not parse_result:
            continue
            
        action, table_name, args = parse_result
        cli_action = command.strip().split()[1].lower()

        if verificar_permissao_cli(permissions, table_name, action):
            print(f"   [Autorizado] Permissão '{table_name}:{action}' concedida. Executando '{cli_action}'...")
            
            # 5. Execução
            result = executar_aws_cli_comando(cli_action, args)
            
            # 6. Exibição do Resultado
            if result:
                if cli_action == 'get-item' and 'Item' in result:
                    print("\n--- Resultado (Deserializado) ---")
                    item = deserialize_item(result['Item'])
                    print(item if item else "Item não encontrado.")
                    print("----------------------------------\n")
                elif cli_action in ['query', 'scan'] and 'Items' in result:
                    print("\n--- Resultados (Deserializados) ---")
                    deserialized_items = [deserialize_item(item) for item in result['Items']]
                    for item in deserialized_items:
                        print(item)
                    print("----------------------------------\n")
                elif cli_action in ['put-item', 'update-item', 'delete-item']:
                    print(f"\n✅ Operação '{cli_action}' concluída com sucesso.\n")
                else:
                    # Para outros comandos, exibe a resposta bruta ou uma mensagem de sucesso
                    print("\n✅ Comando executado com sucesso (sem retorno específico de item).\n")

        else:
            print(f"\n❌ ERRO DE AUTORIZAÇÃO: O usuário '{username}' (papel: {prompt_role}) não tem a permissão **'{table_name}:{action}'** necessária.")
            print("----------------------------------\n")

    print("\nSaindo do cliente AWS CLI autorizado.")

if __name__ == "__main__":
    main()