import httpx
import pytest

# URL base da sua API
BASE_URL = "http://localhost:8080"
LOGIN_URL = f"{BASE_URL}/login"
TEST_TABLE = "customer" # Tabela de teste padrão para permissões gerais de crude

# Credenciais dos usuários (Use as credenciais reais do seu DynamoDB Local)
USERS = {
	"reader": {"username": "reader1", "password": "ReaderPass1"},
	"writer": {"username": "writer1", "password": "WriterPass1"},
	"admin": {"username": "admin1", "password": "AdminPass1"},
}

# --- Fixtures para Tokens ---

@pytest.fixture(scope="session")
def tokens():
	"""
	Fixture que realiza o login para todos os usuários definidos em USERS 
	e armazena seus tokens JWT para uso em todos os testes da sessão.
	
	Returns:
		dict: Um dicionário onde a chave é o papel ('reader', 'writer', 'admin') e o valor é o token JWT.
	"""
	user_tokens = {}
	for role, creds in USERS.items():
		# Usa httpx para enviar a requisição POST de login
		response = httpx.post(
			LOGIN_URL, 
			# Usa 'json=' para enviar o corpo JSON, correspondendo ao modelo Pydantic UserLogin da APIjson={"username": creds["username"], "password": creds["password"]} 
			json={"username": creds["username"], "password": creds["password"]}
		)
			
		response.raise_for_status() # Levanta exceção para status 4xx (client side) ou 5xx (server side)
		token_data = response.json()
		user_tokens[role] = token_data["access_token"]
	return user_tokens

# Dados de teste para POST/PUT
DUMMY_DATA = {
	"key": {"customer_name": "TestUser"},
	"attributes": {"customer_street": "TestStreet", "customer_city":"TestCity"},
}


@pytest.fixture(scope="module", autouse=True)
def setup_test_item(tokens):
	""" 
	Fixture que garante que o item de teste 'TestUser' exista antes de executar 
	os testes do módulo e o remove após a conclusão (limpeza/teardown).
	
	Args:
		tokens (dict): Fixture contendo os tokens JWT.
	
	Yields:
		None: Executa os testes entre o SETUP e o TEARDOWN.
	"""
	admin_token = tokens["admin"] 
	headers = {"Authorization": f"Bearer {admin_token}"}
	url = f"{BASE_URL}/api/{TEST_TABLE}/item"
	
	# SETUP: Cria o item para que os GETs e DELETEs subsequentes funcionem
	print("\n[SETUP] Criando item de teste (TestUser)...")
	
	# Tenta criar (POST) o item usando o token de Admin
	response_post = httpx.post(url, json=DUMMY_DATA, headers=headers)
	
	if response_post.status_code not in [200, 201]:
		print(f"[AVISO] Falha ao criar item de teste. Status: {response_post.status_code}. Detalhe: {response_post.text}")
		
	# Executa todos os testes do módulo
	yield
	
	# TEARDOWN: Remove o item após a execução de todos os testes
	print("\n[TEARDOWN] Removendo item de teste (TestUser)...")
	
	# Delete usa parâmetros de query para a chave
	params_delete = {"key": "customer_name", "key_value": "TestUser"}
	response_delete = httpx.delete(url, params=params_delete, headers=headers)
	
	if response_delete.status_code not in [200, 204]:
		print(f"[AVISO] Falha ao remover item de teste. Status: {response_delete.status_code}. Detalhe: {response_delete.text}")
	else:
		print("[TEARDOWN] Limpeza concluída.")

@pytest.mark.parametrize("role, method, status_code", [
	# 1. Testes do Papel READER (Deve ter acesso de leitura na tabela customer)("reader", "PUT", 403),
	("reader", "POST", 403),
	("reader", "PUT", 403),
	("reader", "GET", 200),
	("reader", "DELETE", 403),

	# 2. Testes do Papel WRITER (Deve ter acesso total na tabela customer)
	("writer", "POST", 200),
	("writer", "PUT", 200),
	("writer", "GET", 200),
	("writer", "DELETE", 200),

	# 3. Testes do Papel ADMIN (Acesso total via Coringa '*')
	("admin", "POST", 200),
	("admin", "PUT", 200),
	("admin", "GET", 200),
	("admin", "DELETE", 200),
])
def test_authorization_matrix(tokens, role, method, status_code):
	""" 
	Testa se cada papel de usuário recebe o status code esperado para cada método 
	HTTP crude na tabela de teste padrão ('customer').
	"""
	token = tokens[role]
	headers = {"Authorization": f"Bearer {token}"}

	url = f"{BASE_URL}/api/{TEST_TABLE}/item"
	data = None
	params = None

	if method == "GET" or method == "DELETE":
		# GET e DELETE usam Query Params para a chave do item
		params = {"key": "customer_name", "key_value": "TestUser"}
	elif method == "POST" or method == "PUT":
		# POST e PUT usam corpo JSON
		data = DUMMY_DATA
	
	# Executa a requisição
	with httpx.Client(headers=headers, timeout=5) as client:
		response = client.request(method, url, json=data, params=params)

	assert response.status_code == status_code
	
# Dados de teste para tabelas sensíveis (users e roles)
SENSITIVE_DATA = {
	"users": {
		"POST": {"key": {"username": "TestSensitiveUser"}, "attributes": {"password_hash": "...", "role": ["reader"]}},
		"GET_KEY": {"key": "username", "key_value": "TestSensitiveUser"}
	},
	"roles": {
		"POST": {"key": {"role_name": "TestSensitiveRole"}, "attributes": {"permissions": ["table:read"]}},
		"GET_KEY": {"key": "role_name", "key_value": "TestSensitiveRole"}
	}
}

@pytest.mark.parametrize("role, method, status_code, table", [
	# Reader em Tabelas Sensíveis (DEVE ser negado, 403)
	("reader", "POST", 403, "users"),
	("reader", "PUT", 403, "users"),
	("reader", "GET", 403, "users"),
	("reader", "DELETE", 403, "users"),
	##
	("reader", "POST", 403, "roles"),
	("reader", "PUT", 403, "roles"),
	("reader", "GET", 403, "roles"),
	("reader", "DELETE", 403, "roles"),

	# Writer em Tabelas Sensíveis (DEVE ser negado, 403)
	("writer", "POST", 403, "users"),
	("writer", "PUT", 403, "users"),
	("writer", "GET", 403, "users"),
	("writer", "DELETE", 403, "users"),
	##
	("writer", "POST", 403, "roles"),
	("writer", "PUT", 403, "roles"),
	("writer", "GET", 403, "roles"),
	("writer", "DELETE", 403, "roles"),

	# Admin em Tabelas Sensíveis (DEVE ser permitido, 200)
	("admin", "POST", 200, "users"),
	("admin", "PUT", 200, "users"),
	("admin", "GET", 200, "users"),
	("admin", "DELETE", 200, "users"),
	##
	("admin", "POST", 200, "roles"),
	("admin", "PUT", 200, "roles"),
	("admin", "GET", 200, "roles"),
	("admin", "DELETE", 200, "roles"),
])
def test_sensitive_table_access(tokens, role, method, status_code, table):
	""" 
	Testa se apenas o ADMIN (que tem o coringa '*') pode acessar as tabelas 
	sensíveis 'users' e 'roles', confirmando que Reader e Writer são negados (403).
	"""
	token = tokens[role]
	headers = {"Authorization": f"Bearer {token}"}
	
	# URL aponta para a tabela sensível
	url = f"{BASE_URL}/api/{table}/item"
	data = None
	params = None
	
	# Configura dados/parâmetros baseados no método e na tabela
	if method == "POST" or method == "PUT":
		# Usa o payload de POST/PUT do SENSITIVE_DATA
		data = SENSITIVE_DATA[table]["POST"]

	elif method == "GET" or method == "DELETE":
		# Usa os Query Params corretos para cada tabela
		params = SENSITIVE_DATA[table]["GET_KEY"]
		
	with httpx.Client(headers=headers, timeout=5) as client:
		response = client.request(method, url, json=data, params=params)

	assert response.status_code == status_code, \
		f"Falha: Papel {role} com {method} na tabela '{table}' retornou {response.status_code}, esperado {status_code}. Detalhe: {response.text}"

