import pytest
import subprocess
from typing import Dict

CLI_CMD = ["python3", "main.py"]

AUTORIZADO="[Autorizado]"
AUTORIZADO_ERRO="ERRO DE AUTORIZAÇÃO"

# --- Usuários reais do seed do DynamoDB ---
USERS: Dict[str, Dict[str, str]] = {
    "reader": {"username": "reader1", "password": "123"},
    "writer": {"username": "writer1", "password": "123"},
    "admin": {"username": "admin1", "password": "123"},
}

# --- Comandos DynamoDB ---
CRUD_COMMANDS = {
    "read": "dynamodb get-item --table-name customer "
            "--key '{\"customer_name\": {\"S\": \"TestUserCLI\"}}'",

    "scan": "dynamodb scan --table-name customer",

    "query": "dynamodb query --table-name customer "
             "--key-condition-expression 'customer_name = :n' "
             "--expression-attribute-values '{\":n\": {\"S\": \"TestUserCLI\"}}'",

    "write": "dynamodb put-item --table-name customer "
             "--item '{\"customer_name\": {\"S\": \"TestUserCLI\"}, "
             "\"customer_city\": {\"S\": \"CLI-City\"}}'",

    "update": "dynamodb update-item --table-name customer "
              "--key '{\"customer_name\": {\"S\": \"TestUserCLI\"}}' "
              "--update-expression \"SET customer_city = :c\" "
              "--expression-attribute-values '{\":c\": {\"S\": \"CLI-Updated\"}}'",

    "delete": "dynamodb delete-item --table-name customer "
              "--key '{\"customer_name\": {\"S\": \"TestUserCLI\"}}'",
}

SENSITIVE_COMMANDS = {
    "users": {
        "read": "dynamodb get-item --table-name users "
                "--key '{\"username\": {\"S\": \"reader1\"}}'",
        
        "scan": "dynamodb scan --table-name users",

        "query": "dynamodb query --table-name users "
                "--key-condition-expression 'username = :n' "
                "--expression-attribute-values '{\":n\": {\"S\": \"TestUserCLI\"}}'",

        "write": "dynamodb put-item --table-name users "
                 "--item '{\"username\": {\"S\": \"x\"}}'",

        "update": "dynamodb update-item --table-name users "
                  "--key '{\"username\": {\"S\": \"x\"}}' "
                  "--update-expression \"SET active = :a\" "
                  "--expression-attribute-values '{\":a\": {\"BOOL\": true}}'",

        "delete": "dynamodb delete-item --table-name users "
                  "--key '{\"username\": {\"S\": \"x\"}}'",
###############################################################
        "read": "dynamodb get-item --table-name roles "
                "--key '{\"role_name\": {\"S\": \"reader\"}}'",
        
        "scan": "dynamodb scan --table-name roles",

        "query": "dynamodb query --table-name roles "
                "--key-condition-expression 'role_name = :n' "
                "--expression-attribute-values '{\":n\": {\"S\": \"TestUserCLI\"}}'",

        "write": "dynamodb put-item --table-name roles "
                 "--item '{\"role_name\": {\"S\": \"x\"}}'",

        "update": "dynamodb update-item --table-name roles "
                  "--key '{\"role_name\": {\"S\": \"x\"}}' "
                  "--update-expression \"SET active = :a\" "
                  "--expression-attribute-values '{\":a\": {\"BOOL\": true}}'",

        "delete": "dynamodb delete-item --table-name roles "
                  "--key '{\"role_name\": {\"S\": \"x\"}}'",
    }
}

# --- Executor REAL do CLI ---

def run_cli(username: str, password: str, command: str) -> str:
    """
    Executa o main.py como um usuário real,
    simulando stdin interativo.
    """
    stdin_payload = f"{username}\n{password}\n{command}\nexit\n"
    #print(command)

    proc = subprocess.run(
        CLI_CMD,
        input=stdin_payload,
        text=True,
        capture_output=True
    )

    return proc.stdout + proc.stderr


# ------------------------------------------------------------------
# TESTES
# ------------------------------------------------------------------

@pytest.mark.parametrize("role, action, expected", [
    ("reader", "read", AUTORIZADO),
    ("reader", "scan", AUTORIZADO),
    ("reader", "query", AUTORIZADO),
    ("reader", "write", AUTORIZADO_ERRO),
    ("reader", "update", AUTORIZADO_ERRO),
    ("reader", "delete", AUTORIZADO_ERRO),

    ("writer", "read", AUTORIZADO),
    ("writer", "scan", AUTORIZADO),
    ("writer", "query", AUTORIZADO),
    ("writer", "write", AUTORIZADO),
    ("writer", "update", AUTORIZADO),
    ("writer", "delete", AUTORIZADO),

    ("admin", "read", AUTORIZADO),
    ("admin", "scan", AUTORIZADO),
    ("admin", "query", AUTORIZADO),
    ("admin", "write", AUTORIZADO),
    ("admin", "update", AUTORIZADO),
    ("admin", "delete", AUTORIZADO),
])
def test_crud_authorization(role, action, expected):
    creds = USERS[role]
    output = run_cli(creds["username"], creds["password"], CRUD_COMMANDS[action])

    assert expected in output, f"\nOUTPUT COMPLETO:\n{output}"

@pytest.mark.parametrize("role, action, expected", [
    ("reader", "read", AUTORIZADO_ERRO),
    ("reader", "scan", AUTORIZADO_ERRO),
    ("reader", "query", AUTORIZADO_ERRO),
    ("reader", "write", AUTORIZADO_ERRO),
    ("reader", "update", AUTORIZADO_ERRO),
    ("reader", "delete", AUTORIZADO_ERRO),

    ("writer", "read", AUTORIZADO_ERRO),
    ("writer", "scan", AUTORIZADO_ERRO),
    ("writer", "query", AUTORIZADO_ERRO),
    ("writer", "write", AUTORIZADO_ERRO),
    ("writer", "update", AUTORIZADO_ERRO),
    ("writer", "delete", AUTORIZADO_ERRO),

    ("admin", "read", AUTORIZADO),
    ("admin", "scan", AUTORIZADO),
    ("admin", "query", AUTORIZADO),
    ("admin", "write", AUTORIZADO),
    ("admin", "update", AUTORIZADO),
    ("admin", "delete", AUTORIZADO),
])
def test_sensitive_users_table(role, action, expected):
    creds = USERS[role]
    output = run_cli(
        creds["username"],
        creds["password"],
        SENSITIVE_COMMANDS["users"][action]
    )

    assert expected in output, f"\nOUTPUT COMPLETO:\n{output}"


def test_invalid_login():
    output = run_cli(
        "nonexistentuser",
        "wrongpassword",
        CRUD_COMMANDS["read"]
    )
    print(output)

    assert "Autenticação falhou" in output
