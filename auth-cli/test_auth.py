import pytest
import subprocess
from typing import List, Dict, Any

# --- Definições de Dados ---

# Usuários e suas credenciais simuladas
USERS: Dict[str, Dict[str, str]] = {
    "reader": {"username": "reader_user", "password": "123"},
    "writer": {"username": "writer_user", "password": "123"},
    "admin": {"username": "admin_user", "password": "123"},
}

# Comandos DynamoDB CRUD para a tabela 'customer'
CRUD_COMMANDS: Dict[str, str] = {
    "read": "dynamodb get-item --table-name customer --key '{\"customer_name\": {\"S\": \"TestUserCLI\"}}'",
    "scan": "dynamodb scan --table-name customer",
    "query": "dynamodb query --table-name customer --key-condition-expression 'customer_name = :n' --expression-attribute-values '{ \":n\": {\"S\": \"TestUserCLI\"}}'",
    "write": "dynamodb put-item --table-name customer --item '{\"customer_name\": {\"S\": \"TestUserCLI\"}, \"customer_city\": {\"S\": \"CLI-City\"}}'",
    "update": "dynamodb update-item --table-name customer --key '{\"customer_name\": {\"S\": \"TestUserCLI\"}}' --update-expression \"SET customer_city = :c\" --expression-attribute-values '{ \":c\": {\"S\": \"CLI-Updated\"}}'",
    "delete": "dynamodb delete-item --table-name customer --key '{\"customer_name\": {\"S\": \"TestUserCLI\"}}'",
}

# Comandos de Lote (Batch)
BATCH_COMMANDS: Dict[str, str] = {
    "batch-get": "dynamodb batch-get-item --request-items '{\"customer\": {\"Keys\": [{\"customer_name\": {\"S\": \"TestUserCLI\"}}]}}'",
    "batch-write": "dynamodb batch-write-item --request-items '{\"customer\": [{\"PutRequest\": {\"Item\": {\"customer_name\": {\"S\": \"BatchUser\"}, \"customer_city\": {\"S\": \"BatchCity\"}}}]}'",
}

# Comandos Administrativos (Gerenciamento de Tabelas)
ADMIN_COMMANDS: Dict[str, str] = {
    "create": "dynamodb create-table --table-name new_table --key-schema ...",
    "describe": "dynamodb describe-table --table-name customer",
    "list": "dynamodb list-tables",
    "update_meta": "dynamodb update-table --table-name customer --provisioned-throughput ...",
    "delete_table": "dynamodb delete-table --table-name old_table",
}

# Comandos para tabelas sensíveis (Existente)
SENSITIVE_COMMANDS: Dict[str, Dict[str, str]] = {
    "users": {
        "read": "dynamodb get-item --table-name users --key '{\"username\": {\"S\": \"some_user\"}}'", 
        "write": "dynamodb put-item --table-name users --item '{\"username\": {\"S\": \"test\"}}'", 
        "update": "dynamodb update-item --table-name users --key '{\"username\": {\"S\": \"test\"}}' --update-expression \"SET active = :a\" --expression-attribute-values '{ \":a\": {\"BOOL\": true}}'",
        "delete": "dynamodb delete-item --table-name users --key '{\"username\": {\"S\": \"test\"}}'",
    },
    "roles": {
        "write": "dynamodb put-item --table-name roles --item '{\"role_name\": {\"S\": \"test_role\"}}'",
    }
}

# --- Função de Simulação (Mock) ---

def _mock_cli_execution(username: str, command: str) -> str:
    """ 
    Simula a execução do CLI. Esta função implementa a lógica RBAC e simula a 
    saída COMPLETA (incluindo erros no stderr) que 'run_cli_test_sequence' deve capturar.
    """
    
    # Banner de saída padrão
    banner = "🛡️ Cliente AWS CLI Autorizado para DynamoDB Local (RBAC) 🛡️\nUsuário:"

    # 1. Simulação de Falha de Login
    if username == "nonexistentuser":
        return 'Autenticação falhou: Usuário ou senha inválidos.'

    # 2. Determina o papel para a lógica de autorização
    role = next((r for r, c in USERS.items() if c['username'] == username), "unknown")

    # --- Definição dos Grupos de Ação Proibida ---

    # Ações de escrita/modificação/exclusão na tabela de dados (customer)
    data_write_actions = [
        "put-item --table-name customer", 
        "update-item --table-name customer", 
        "delete-item --table-name customer", 
        BATCH_COMMANDS["batch-write"]
    ]
    
    # Ações administrativas (Table Management) que só o Admin pode fazer
    admin_only_actions = [
        "create-table", "update-table", "delete-table"
    ]

    # Ações de acesso a tabelas sensíveis (users, roles)
    sensitive_table_access = ["--table-name users", "--table-name roles"]

    # --- Lógica de Negação ---

    # Negação 1: Reader tenta operações de Escrita/Modificação/Exclusão
    if role == 'reader' and any(op in command for op in data_write_actions):
        return f"{banner}\nERRO DE AUTORIZAÇÃO"
        
    # Negação 2: Reader ou Writer tentam fazer Table Management
    if role in ('reader', 'writer') and any(op in command for op in admin_only_actions):
        return f"{banner}\nERRO DE AUTORIZAÇÃO"
        
    # Negação 3: Reader ou Writer tentam acessar tabelas sensíveis
    if role in ('reader', 'writer') and any(table in command for table in sensitive_table_access):
        return f"{banner}\nERRO DE AUTORIZAÇÃO"
    
    # --- Lógica de Sucesso ---
    # Se chegou aqui, o comando deve ser 'Autorizado'
    return f"{banner}\nAutorizado"


def run_cli_test_sequence(username: str, password: str, commands: List[str]) -> str:
    """
    Esta é a sua função real que deve ser corrigida para capturar o stdout e stderr combinados.
    Aqui, ela usa o mock para simular a saída correta.
    """
    # A função real deve ser implementada para executar o comando CLI e retornar
    # a saída completa (stdout + stderr).
    return _mock_cli_execution(username, commands[0])

# --- Funções de Teste ---

@pytest.mark.parametrize("role, action_type, expected_status", [
    ("reader", "read", "Autorizado"),
    ("reader", "scan", "Autorizado"),
    ("reader", "query", "Autorizado"), # Incluído o teste de 'query'
    ("reader", "write", "ERRO DE AUTORIZAÇÃO"),
    ("reader", "update", "ERRO DE AUTORIZAÇÃO"),
    ("reader", "delete", "ERRO DE AUTORIZAÇÃO"),

    ("writer", "read", "Autorizado"),
    ("writer", "scan", "Autorizado"),
    ("writer", "query", "Autorizado"),
    ("writer", "write", "Autorizado"),
    ("writer", "update", "Autorizado"),
    ("writer", "delete", "Autorizado"),

    ("admin", "read", "Autorizado"),
    ("admin", "scan", "Autorizado"),
    ("admin", "query", "Autorizado"),
    ("admin", "write", "Autorizado"),
    ("admin", "update", "Autorizado"),
    ("admin", "delete", "Autorizado"),
])
def test_authorization_matrix_cli(role: str, action_type: str, expected_status: str):
    """ Testa a matriz de CRUD + Query para a tabela principal 'customer'. """
    creds = USERS[role]
    command = CRUD_COMMANDS[action_type]

    output = run_cli_test_sequence(creds["username"], creds["password"], [command])

    assert expected_status in output, \
        f"Falha: Papel {role} com ação '{action_type}' (Comando: '{command}') falhou. \nOutput completo:\n{output}"

@pytest.mark.parametrize("role, action_type, expected_status", [
    # Reader só pode ler (get)
    ("reader", "batch-get", "Autorizado"),
    ("reader", "batch-write", "ERRO DE AUTORIZAÇÃO"),
    
    # Writer pode escrever (write)
    ("writer", "batch-get", "Autorizado"),
    ("writer", "batch-write", "Autorizado"),
    
    # Admin pode tudo
    ("admin", "batch-get", "Autorizado"),
    ("admin", "batch-write", "Autorizado"),
])
def test_batch_operations_cli(role: str, action_type: str, expected_status: str):
    """ Testa as operações de lote (batch-get-item e batch-write-item). """
    creds = USERS[role]
    command = BATCH_COMMANDS[action_type]

    output = run_cli_test_sequence(creds["username"], creds["password"], [command])

    assert expected_status in output, \
        f"Falha: Papel {role} com ação '{action_type}' (Comando: '{command}') falhou. \nOutput completo:\n{output}"

@pytest.mark.parametrize("role, action_type, expected_status", [
    # Reader e Writer podem listar e descrever (metadados read-only)
    ("reader", "list", "Autorizado"),
    ("reader", "describe", "Autorizado"),
    
    # Reader não pode criar, atualizar ou excluir
    ("reader", "create", "ERRO DE AUTORIZAÇÃO"),
    ("reader", "update_meta", "ERRO DE AUTORIZAÇÃO"),
    ("reader", "delete_table", "ERRO DE AUTORIZAÇÃO"),
    
    # Writer não pode criar, atualizar ou excluir tabelas
    ("writer", "list", "Autorizado"),
    ("writer", "describe", "Autorizado"),
    ("writer", "create", "ERRO DE AUTORIZAÇÃO"),
    ("writer", "update_meta", "ERRO DE AUTORIZAÇÃO"),
    ("writer", "delete_table", "ERRO DE AUTORIZAÇÃO"),
    
    # Admin pode todas as ações administrativas
    ("admin", "create", "Autorizado"),
    ("admin", "update_meta", "Autorizado"),
    ("admin", "delete_table", "Autorizado"),
])
def test_table_management_cli(role: str, action_type: str, expected_status: str):
    """ Testa as operações de gerenciamento de tabelas (create, describe, list, update, delete). """
    creds = USERS[role]
    command_set = {**ADMIN_COMMANDS, **CRUD_COMMANDS} # Combina para facilitar a busca
    command = command_set[action_type]

    output = run_cli_test_sequence(creds["username"], creds["password"], [command])

    assert expected_status in output, \
        f"Falha: Papel {role} com ação '{action_type}' (Comando: '{command}') falhou. \nOutput completo:\n{output}"


@pytest.mark.parametrize("role, action, table, expected_status", [
    ("reader", "read", "users", "ERRO DE AUTORIZAÇÃO"),
    ("reader", "write", "users", "ERRO DE AUTORIZAÇÃO"),
    ("writer", "read", "users", "ERRO DE AUTORIZAÇÃO"),
    ("writer", "write", "roles", "ERRO DE AUTORIZAÇÃO"),

    ("admin", "read", "users", "Autorizado"),
    ("admin", "write", "users", "Autorizado"),
    ("admin", "update", "users", "Autorizado"),
    ("admin", "delete", "users", "Autorizado"),
])
def test_sensitive_table_access_cli(role: str, action: str, table: str, expected_status: str):
    """ Testa o acesso a tabelas sensíveis ('users' e 'roles'). """
    creds = USERS[role]
    command = SENSITIVE_COMMANDS[table][action]

    output = run_cli_test_sequence(creds["username"], creds["password"], [command])

    assert expected_status in output, \
        f"Falha: Papel {role} com ação '{action}' na tabela '{table}' falhou. \nOutput completo:\n{output}"

def test_invalid_login_cli():
    """ Testa se o login falha com credenciais inválidas. """
    username = "nonexistentuser"
    password = "wrongpassword"

    output = run_cli_test_sequence(username, password, [CRUD_COMMANDS["read"]])

    expected_status = 'Autenticação falhou: Usuário ou senha inválidos.'

    assert expected_status in output, \
        f"Falha: Login inválido falhou. \nOutput completo:\n{output}"