import pytest
import subprocess
from typing import Dict

CLI_CMD = ["python3", "main.py"]

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

        "write": "dynamodb put-item --table-name users "
                 "--item '{\"username\": {\"S\": \"x\"}}'",

        "update": "dynamodb update-item --table-name users "
                  "--key '{\"username\": {\"S\": \"x\"}}' "
                  "--update-expression \"SET active = :a\" "
                  "--expression-attribute-values '{\":a\": {\"BOOL\": true}}'",

        "delete": "dynamodb delete-item --table-name users "
                  "--key '{\"username\": {\"S\": \"x\"}}'",
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
    ("reader", "read", "[Autorizado]"),
    ("reader", "scan", "[Autorizado]"),
    ("reader", "query", "[Autorizado]"),
    ("reader", "write", "ERRO DE AUTORIZAÇÃO"),
    ("reader", "update", "ERRO DE AUTORIZAÇÃO"),
    ("reader", "delete", "ERRO DE AUTORIZAÇÃO"),

    ("writer", "read", "[Autorizado]"),
    ("writer", "scan", "[Autorizado]"),
    ("writer", "query", "[Autorizado]"),
    ("writer", "write", "[Autorizado]"),
    ("writer", "update", "[Autorizado]"),
    ("writer", "delete", "[Autorizado]"),

    ("admin", "read", "[Autorizado]"),
    ("admin", "write", "[Autorizado]"),
    ("admin", "delete", "[Autorizado]"),
])
def test_crud_authorization(role, action, expected):
    creds = USERS[role]
    output = run_cli(creds["username"], creds["password"], CRUD_COMMANDS[action])

    assert expected in output, f"\nOUTPUT COMPLETO:\n{output}"

@pytest.mark.parametrize("role, action, expected", [
    ("reader", "read", "ERRO DE AUTORIZAÇÃO"),
    ("writer", "write", "ERRO DE AUTORIZAÇÃO"),
    ("admin", "delete", "[Autorizado]"),
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

    assert "Autenticação falhou" in output
