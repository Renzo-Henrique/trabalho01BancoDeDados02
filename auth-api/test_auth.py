import pytest
import subprocess
import os
import re

# Caminho para o script CLI dentro do container
CLI_PATH = "/app/auth_cli.py"

# Credenciais dos usuários (As mesmas usadas na CLI)
USERS = {
	"reader": {"username": "reader1", "password": "ReaderPass1"},
	"writer": {"username": "writer1", "password": "WriterPass1"},
	"admin": {"username": "admin1", "password": "AdminPass1"},
}

# Dados de teste para CRUD na tabela 'customer'
TEST_TABLE = "customer"

# --- Dados de Teste: Entrada e Verificação ---

# Define os comandos PartiQL e as verificações esperadas
# (comando, resultado_esperado_no_output, tipo_de_tabela)

# Comandos de CRUD
CRUD_COMMANDS = {
	"read": f"SELECT * FROM {TEST_TABLE} WHERE customer_name='TestUser'",
	"write": f"INSERT INTO {TEST_TABLE} VALUE {{'customer_name':'TestUser', 'customer_city':'CLI-City'}}",
	"update": f"UPDATE {TEST_TABLE} SET customer_city='CLI-Updated' WHERE customer_name='TestUser'",
	"delete": f"DELETE FROM {TEST_TABLE} WHERE customer_name='TestUser'",
}

# Comandos para Tabelas Sensíveis
SENSITIVE_COMMANDS = {
	"users": {
		"read": "SELECT username FROM users",
		"write": "INSERT INTO users VALUE {'username':'TestCLINewUser', 'password':'...'}",
		"update": "UPDATE users SET password='UpdatedPwd' WHERE username='TestCLINewUser'",
		"delete": "DELETE FROM users WHERE username='TestCLINewUser'"
	},
	"roles": {
		"read": "SELECT role_name FROM roles",
		"write": "INSERT INTO roles VALUE {'role_name':'TestCLINewRole', 'permissions':['loan:read']}",
		"update": "UPDATE roles SET permissions=list_append(permissions, ['account:read']) WHERE role_name='TestCLINewRole'",
		"delete": "DELETE FROM roles WHERE role_name='TestCLINewRole'"
	}
}


def run_cli_test_sequence(username, password, commands):
	"""
	Executa o auth_cli.py como um subprocesso, fornecendo entrada (login + comandos) 
	e retornando a saída.
	
	Args:
		username (str): Usuário para login.
		password (str): Senha para login.
		commands (list): Lista de comandos PartiQL a serem executados.

	Returns:
		str: Toda a saída (stdout) do processo.
	"""
	# Combina login, comandos e 'exit'
	input_sequence = [username, password] + commands + ['exit']
	input_str = "\n".join(input_sequence) + "\n"

	# Usa o 'subprocess.run' para executar o script e capturar a saída
	try:
		result = subprocess.run(
			# O binário python pode estar em '/usr/bin/python' ou 'python'
			# Use 'python' para que o sistema use o PATH do container:
			["python", CLI_PATH], 
			input=input_str, # <--- ENVIE APENAS A STRING
			capture_output=True,
			text=True, # text=True significa que a entrada (input) é esperada como string, e a saída (stdout/stderr) será decodificada para string.
			check=False,
			timeout=10 
		)
		return result.stdout.strip()
	except subprocess.TimeoutExpired:
		return "TIMEOUT_EXPIRED"
	except FileNotFoundError:
		# Se o pytest não estiver rodando no ambiente correto (container)
		return f"ERROR: CLI script not found at {CLI_PATH}"


# --- Fixture de Setup/Teardown para o Item de Teste ---

@pytest.fixture(scope="module", autouse=True)
def setup_test_item_cli():
	""" 
	Garante que o item de teste 'TestUser' exista antes do módulo de teste 
	e o remove após (usando o papel admin).
	"""
	admin_creds = USERS["admin"]
	
	# 1. SETUP: Criar item de teste (Para testes de GET e DELETE)
	setup_commands = [
		CRUD_COMMANDS["write"] # Usa o comando INSERT (write)
	]
	print("\n[SETUP CLI] Criando item de teste (TestUser)...")
	run_cli_test_sequence(admin_creds["username"], admin_creds["password"], setup_commands)
	
	yield # Executa os testes do módulo
	
	# 2. TEARDOWN: Remover item de teste
	teardown_commands = [
		CRUD_COMMANDS["delete"] # Usa o comando DELETE
	]
	print("\n[TEARDOWN CLI] Removendo item de teste (TestUser)...")
	run_cli_test_sequence(admin_creds["username"], admin_creds["password"], teardown_commands)
	print("[TEARDOWN CLI] Limpeza concluída.")


# --- 2. Teste da Matriz de Autorização (CRUD) ---

@pytest.mark.parametrize("role, action, expected_status", [
	# 1. Papel READER (Permite apenas read)
	("reader", "read", "Autorizado"),
	("reader", "write", "ERRO DE AUTORIZAÇÃO"),
	("reader", "update", "ERRO DE AUTORIZAÇÃO"),
	("reader", "delete", "ERRO DE AUTORIZAÇÃO"),

	# 2. Papel WRITER (Permite CRUD)
	("writer", "read", "Autorizado"),
	("writer", "write", "Autorizado"),
	("writer", "update", "Autorizado"),
	("writer", "delete", "Autorizado"),

	# 3. Papel ADMIN (Permite CRUD via coringa)
	("admin", "read", "Autorizado"),
	("admin", "write", "Autorizado"),
	("admin", "update", "Autorizado"),
	("admin", "delete", "Autorizado"),
])
def test_authorization_matrix_cli(role, action, expected_status):
	""" Testa se cada papel recebe a mensagem de Autorizado ou ERRO DE AUTORIZAÇÃO esperada. """
	creds = USERS[role]
	command = CRUD_COMMANDS[action]
	
	# Executa a sequência de login e comando
	output = run_cli_test_sequence(creds["username"], creds["password"], [command])
	
	# Verifica se a mensagem de status esperada está presente na saída
	assert expected_status in output, \
		f"Falha: Papel {role} com ação '{action}' (Comando: '{command}') falhou. \nOutput completo:\n{output}"

# --- 3. Teste de Acesso a Tabelas Sensíveis ---

@pytest.mark.parametrize("role, action, table, expected_status", [
	# 1. Reader em Tabelas Sensíveis (DEVE ser negado - 403)
	("reader", "read", "users", "ERRO DE AUTORIZAÇÃO"),
	("reader", "write", "users", "ERRO DE AUTORIZAÇÃO"),
	("reader", "update", "users", "ERRO DE AUTORIZAÇÃO"),
	("reader", "delete", "users", "ERRO DE AUTORIZAÇÃO"),
	##
	("reader", "read", "roles", "ERRO DE AUTORIZAÇÃO"),
	("reader", "write", "roles", "ERRO DE AUTORIZAÇÃO"),
	("reader", "update", "roles", "ERRO DE AUTORIZAÇÃO"),
	("reader", "delete", "roles", "ERRO DE AUTORIZAÇÃO"),

	# 2. Writer em Tabelas Sensíveis (DEVE ser negado - 403)
	("writer", "read", "users", "ERRO DE AUTORIZAÇÃO"),
	("writer", "write", "users", "ERRO DE AUTORIZAÇÃO"),
	("writer", "update", "users", "ERRO DE AUTORIZAÇÃO"),
	("writer", "delete", "users", "ERRO DE AUTORIZAÇÃO"),
	##
	("writer", "read", "roles", "ERRO DE AUTORIZAÇÃO"),
	("writer", "write", "roles", "ERRO DE AUTORIZAÇÃO"),
	("writer", "update", "roles", "ERRO DE AUTORIZAÇÃO"),
	("writer", "delete", "roles", "ERRO DE AUTORIZAÇÃO"),
	
	# 3. Admin em Tabelas Sensíveis (DEVE ser permitido - 200)
	("admin", "read", "users", "Autorizado"),
	("admin", "write", "users", "Autorizado"),
	("admin", "update", "users", "Autorizado"),
	("admin", "delete", "users", "Autorizado"),
	##
	("admin", "read", "roles", "Autorizado"),
	("admin", "write", "roles", "Autorizado"),
	("admin", "update", "roles", "Autorizado"),
	("admin", "delete", "roles", "Autorizado"),
])
# Trecho da função test_sensitive_table_access_cli (Ajustado)

def test_sensitive_table_access_cli(role, action, table, expected_status):
	creds = USERS[role]
	
	# 1. SETUP: Se a ação for UPDATE ou DELETE, garantimos que o item exista (APENAS com Admin)
	setup_commands = []
	if role == "admin" and (action == "update" or action == "delete"):
		# Se for admin, precisamos do item antes de tentar atualizar/deletar
		admin_creds = USERS["admin"]
		setup_commands = [SENSITIVE_COMMANDS[table]["write"]]
		# Executa o setup de criação de item
		run_cli_test_sequence(admin_creds["username"], admin_creds["password"], setup_commands)

	# 2. EXECUÇÃO DO COMANDO PRINCIPAL
	command = SENSITIVE_COMMANDS[table][action] 
	
	# 3. TEARDOWN: Adiciona comandos de cleanup para o Admin (write, update e delete criam/modificam)
	cleanup_commands = []
	# Se o admin executou write/update/delete com sucesso, ou se a ação principal for delete,
	# garantimos que o item seja removido
	if role == "admin":
		if action in ["write", "update"]:
			# Se criou/atualizou, deleta no final
			cleanup_commands = [SENSITIVE_COMMANDS[table]["delete"]]
		elif action == "delete":
			# Se a ação principal era delete, precisamos recriar e deletar de novo no teardown.
			# No entanto, a forma mais simples é deixar a recriação para o próximo teste de 'write'
			# e focar que a execução foi Autorizada/Negada.
			pass

	# Executa a sequência de login, comando e cleanup (se for admin/write/update)
	output = run_cli_test_sequence(creds["username"], creds["password"], [command] + cleanup_commands)
	
	assert expected_status in output, \
		f"Falha: Papel {role} com ação '{action}' na tabela '{table}' falhou. \nOutput completo:\n{output}"
	
# --- 4. Teste de Autenticação Inválida ---
def test_invalid_login_cli():
	""" Testa se o login falha com credenciais inválidas. """
	username = "nonexistentuser"
	password = "wrongpassword"
	
	# Executa o login com credenciais falsas
	output = run_cli_test_sequence(username, password, ["SELECT * FROM customer"])
	
	# A mensagem de falha de autenticação deve estar presente
	assert "Autenticação falhou: Usuário ou senha inválidos." in output
	assert "✅ Autenticado" not in output