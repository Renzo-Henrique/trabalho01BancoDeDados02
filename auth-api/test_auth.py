import httpx
import pytest

# URL base da sua API
BASE_URL = "http://localhost:8080"
LOGIN_URL = f"{BASE_URL}/login"
TEST_TABLE = "customer" # Tabela de teste padrão

# Credenciais dos usuários (Use as credenciais reais do seu DynamoDB Local)
USERS = {
	"reader": {"username": "reader1", "password": "ReaderPass1"},
	"writer": {"username": "writer1", "password": "WriterPass1"},
	"admin": {"username": "admin1", "password": "AdminPass1"},
}

# --- Fixtures para Tokens ---

@pytest.fixture(scope="session")
def tokens():
	# ...
	user_tokens = {}
	for role, creds in USERS.items():
		response = httpx.post(
			LOGIN_URL, 
			# 💡 Use 'json=' para corresponder ao modelo Pydantic UserLogin
			json={"username": creds["username"], "password": creds["password"]} 
		)
		# ⚠️ Adicione este bloco temporário para capturar o erro 422
		if response.status_code == 422:
			print(f"\n--- DEBUG 422 ---")
			print(f"URL: {response.url}")
			print(f"Headers enviados: {response.request.headers}")
			print(f"Corpo JSON enviado: {creds}")
			print(f"Resposta 422 do servidor: {response.text}")
			print(f"-------------------\n")

			
		response.raise_for_status() 
		token_data = response.json()
		user_tokens[role] = token_data["access_token"]
		# ...
	return user_tokens

# Dados de teste para POST/PUT
DUMMY_DATA = {
	"key": {"customer_name": "TestUser"},
	"attributes": {"customer_street": "TestStreet", "customer_city":"TestCity"},
}

# --- NOVA FIXTURE DE SETUP E TEARDOWN ---

@pytest.fixture(scope="module", autouse=True)
def setup_test_item(tokens):
	""" 
	Cria o item de teste antes dos testes (SETUP) usando o token do admin 
	e o deleta após os testes (TEARDOWN).
	"""
	admin_token = tokens["admin"] 
	headers = {"Authorization": f"Bearer {admin_token}"}
	url = f"{BASE_URL}/api/{TEST_TABLE}/item"
	
	# SETUP: Cria o item para que os GETs e DELETEs subsequentes funcionem
	print("\n[SETUP] Criando item de teste (TestUser)...")
	
	# 1. Tentar criar (POST)
	response_post = httpx.post(url, json=DUMMY_DATA, headers=headers)
	
	# Se o item já existir (o que não deve causar erro se for um PUT/POST idempotente), 
	# ou se for a primeira vez, o status deve ser 200/201.
	if response_post.status_code not in [200, 201]:
		print(f"[AVISO] Falha ao criar item de teste. Status: {response_post.status_code}. Detalhe: {response_post.text}")
		
	# 2. Executar os testes que dependem deste item
	yield
	
	# TEARDOWN: Remove o item após a execução de todos os testes
	print("\n[TEARDOWN] Removendo item de teste (TestUser)...")
	
	# Os GET e DELETE usam parâmetros de query
	params_delete = {"key": "customer_name", "key_value": "TestUser"}
	response_delete = httpx.delete(url, params=params_delete, headers=headers)
	
	if response_delete.status_code not in [200, 204]:
		print(f"[AVISO] Falha ao remover item de teste. Status: {response_delete.status_code}. Detalhe: {response_delete.text}")
	else:
		print("[TEARDOWN] Limpeza concluída.")

@pytest.mark.parametrize("role, method, status_code", [
	# 1. Testes do Papel READER (Deve ler, deve ser negado para escrita/deleção)
	("reader", "GET", 200),
	("reader", "PUT", 403),
	("reader", "POST", 403),
	("reader", "DELETE", 403),

	# 2. Testes do Papel WRITER (Deve ter acesso total na tabela customer)
	("writer", "POST", 200), # ou 201 Created, dependendo da sua API
	("writer", "PUT", 200),
	("writer", "GET", 200),
	("writer", "DELETE", 200), # Assume que conseguiremos deletar o item de teste

	# 3. Testes do Papel ADMIN (Acesso total via Coringa '*')
	("admin", "POST", 200),
	("admin", "PUT", 200),
	("admin", "GET", 200),
	("admin", "DELETE", 200),
])
def test_authorization_matrix(tokens, role, method, status_code):
	""" Testa se cada papel recebe o status code esperado para cada método. """

	token = tokens[role]
	headers = {"Authorization": f"Bearer {token}"}

	# Define URL e corpo da requisição
	url = f"{BASE_URL}/api/{TEST_TABLE}/item"
	data = None
	params = None

	if method == "GET" or method == "DELETE":
		# GET e DELETE usam Query Params para a chave. 
		# Precisamos garantir que um item 'TestUser' exista antes de DELETE.
		params = {"key": "customer_name", "key_value": "TestUser"}
	elif method == "POST" or method == "PUT":
		# POST e PUT usam corpo JSON
		data = DUMMY_DATA
	
	# Executa a requisição
	with httpx.Client(headers=headers, timeout=5) as client:
		response = client.request(method, url, json=data, params=params)

	assert response.status_code == status_code
    # Se você quiser um detalhe mínimo, pode usar:
    # assert response.status_code == status_code, f"Papel {role} com {method} falhou. Detalhe: {response.text}"
