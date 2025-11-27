import os
import json
from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
from jose import JWTError, jwt

# --- 1. CONFIGURAÇÃO E CLIENTE DYNAMODB ---

# O endpoint do DynamoDB é lido das variáveis de ambiente
DYNAMODB_ENDPOINT = os.getenv("DYNAMODB_ENDPOINT", "http://localhost:8000")
REGION = os.getenv("AWS_REGION", "us-west-2")

# Configuração simulada para o DynamoDB Local
dynamodb = boto3.resource(
	'dynamodb',
	endpoint_url=DYNAMODB_ENDPOINT,
	region_name=REGION,
	aws_access_key_id='local',
	aws_secret_access_key='local'
)
# Referência às tabelas de configuração
users_table = dynamodb.Table('users')
roles_table = dynamodb.Table('roles')

app = FastAPI(title="DynamoDB Auth Proxy API")

# --- 2. CONFIGURAÇÃO JWT ---
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "seu-segredo-super-secreto")
ALGORITHM = "HS256"
# Define o esquema OAuth2 e o endpoint onde o token deve ser obtido
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def create_access_token(data: dict):
	""" 
	Cria um token JWT (JSON Web Token) assinado contendo os dados do usuário.

	Args:
		data (dict): Payload a ser codificado (ex: {"sub": "username", "role": ["role_name"]}).

	Returns:
		str: O token JWT codificado.
	"""
	to_encode = data.copy()
	return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- 3. MODELOS Pydantic (Para validação de dados) ---
class UserLogin(BaseModel):
	"""
	Modelo para dados de login de usuário.
	"""
	username: str
	password: str # NOTE:: Senhas em texto puro!

class UserToken(BaseModel):
	"""
	Modelo interno para representar o usuário autenticado, extraído do JWT.
	"""
	username: str
	role_name: str

class DynamoDBRequest(BaseModel):
	"""
	Modelo para as requisições de escrita/atualização no proxy.
	"""
	key: dict # A chave primária (ex: {"customer_name": "Bob"})
	attributes: dict = {} # Os atributos do item a serem inseridos ou atualizados
	
# --- 4. LÓGICA DE AUTORIZAÇÃO ---

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserToken:
	""" 
	Decodifica e valida o JWT para extrair o usuário e o papel. 
	Usado como dependência de autenticação para proteger endpoints.

	Args:
		token (str): O JWT do cabeçalho Authorization: Bearer.

	Raises:
		HTTPException: 401 UNAUTHORIZED se o token for inválido, expirado ou não contiver um papel válido.

	Returns:
		UserToken: Objeto contendo o nome de usuário e o papel.
	"""
	credentials_exception = HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="Credenciais inválidas ou token expirado",
		headers={"WWW-Authenticate": "Bearer"},
	)
	try:
		# Decodifica o token
		payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
		username: str = payload.get("sub")
		role_data: str = payload.get("role")
		
		# Garante que role_name é uma string única
		role_name: str
		if isinstance(role_data, list) and role_data:
			role_name = role_data[0] # TODO:: Pega o primeiro papel apenas
		elif isinstance(role_data, str):
			role_name = role_data
		else:
			raise credentials_exception # Não encontrou um papel válido

		if username is None:
			raise credentials_exception
			
		return UserToken(username=username, role_name=role_name)
	except JWTError:
		# Captura erros de assinatura, expiração, etc.
		raise credentials_exception

async def check_permission(
	user: UserToken = Depends(get_current_user), 
	table_name: str = "default", 
	action: str = "read"
):
	""" 
	Verifica se o papel do usuário tem permissão para a ação ('read', 'write', etc.) na tabela.
	Esta é a função central de Autorização (RBAC).

	Args:
		user (UserToken): Usuário e papel autenticados (obtido via Depends).
		table_name (str): Nome da tabela alvo (ex: 'customer', 'users').
		action (str): Ação desejada (ex: 'read', 'write', 'delete').

	Raises:
		HTTPException: 403 FORBIDDEN se a permissão não for encontrada para o papel.

	Returns:
		bool: True se a permissão for concedida.
	"""
	permission_string = f"{table_name}:{action}"
	role_name = user.role_name

	# 1. Busca as permissões do papel no DynamoDB
	try:
		response = roles_table.get_item(Key={'role_name': role_name})
		role_item = response.get('Item')

		if not role_item:
			raise HTTPException(status_code=403, detail=f"Papel '{role_name}' não encontrado.")

		# O Boto3 Resource geralmente deserializa o tipo 'L' do DynamoDB para uma lista Python.
		permissions = role_item.get('permissions', [])

		if not isinstance(permissions, list):
			permissions = []

		# 2. Verifica a permissão (Coringa ou Permissão Específica)
		if "*" in permissions or permission_string in permissions:
			return True
		
		# 3. Não Autorizado
		raise HTTPException(
			status_code=403,
			detail=f"Usuário não autorizado: Necessária permissão '{permission_string}'."
		)

	except ClientError as e:
		# Captura erros de comunicação com o DynamoDB
		print(f"Erro ao buscar permissões: {e}")
		raise HTTPException(status_code=500, detail="Erro interno de autorização.")

# --- Funções Auxiliares de Autorização (Dependências) ---
async def authorize_read(table_name: str, current_user: UserToken = Depends(get_current_user)):
	""" Dependência para verificar permissão de 'read' em uma tabela específica. """
	return await check_permission(user=current_user, table_name=table_name, action="read")

async def authorize_write(table_name: str, current_user: UserToken = Depends(get_current_user)):
	""" Dependência para verificar permissão de 'write' em uma tabela específica. """
	return await check_permission(user=current_user, table_name=table_name, action="write")

async def authorize_delete(table_name: str, current_user: UserToken = Depends(get_current_user)):
	""" Dependência para verificar permissão de 'delete' em uma tabela específica. """
	return await check_permission(user=current_user, table_name=table_name, action="delete")

async def authorize_update(table_name: str, current_user: UserToken = Depends(get_current_user)):
	""" Dependência para verificar permissão de 'update' em uma tabela específica. """
	return await check_permission(user=current_user, table_name=table_name, action="update")

# --- 5. ENDPOINTS DE AUTENTICAÇÃO E TESTE ---

@app.post("/login", summary="Autenticação e Geração de Token JWT")
async def login_for_access_token(form_data: UserLogin):
	"""
	Verifica as credenciais do usuário na tabela 'users' (simulação de hash com senha em texto puro)
	e retorna um JWT contendo o papel do usuário.
	"""
	try:
		response = users_table.get_item(Key={'username': form_data.username})
		user_item = response.get('Item')

		# Verifica se o usuário existe e se a senha coincide
		if not user_item or user_item.get('password') != form_data.password:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Nome de usuário ou senha inválidos",
				headers={"WWW-Authenticate": "Bearer"},
			)
		
		# Cria o JWT com o username e o papel (role_name)
		access_token = create_access_token(
			data={"sub": user_item['username'], "role": user_item['role_name']}
		)
		return {"access_token": access_token, "token_type": "bearer"}
		
	except ClientError as e:
		"""
		Endpoint de teste simples que retorna os dados do usuário autenticado a partir do token.
		"""
		raise HTTPException(status_code=500, detail="Erro no serviço de autenticação.")

@app.get("/users/me", summary="Testa o Token e Retorna Informações do Usuário")
async def read_users_me(current_user: UserToken = Depends(get_current_user)):
	return {"username": current_user.username, "role": current_user.role_name}

# --- 6. ENDPOINTS DE PROXY DO DYNAMODB (COM AUTORIZAÇÃO) ---

@app.get("/api/{table_name}/item", summary="Proxy para GetItem/Read (Consulta Autorizada)")
async def get_item_proxy(
	table_name: str, 
	key: str, 
	key_value: str,
	# Chama a dependência para verificar permissão de 'read'
	authorized: bool = Depends(authorize_read) 
):
	"""
	Executa um GetItem no DynamoDB APENAS se o usuário tiver permissão '{tabela}:read'.
	
	Args:
		table_name (str): Tabela alvo.
		key (str): Nome da chave primária.
		key_value (str): Valor da chave primária.
	"""
	try:
		table = dynamodb.Table(table_name)
		response = table.get_item(Key={key: key_value})
		
		if 'Item' not in response:
			raise HTTPException(status_code=404, detail=f"Item não encontrado na tabela {table_name}.")
			
		return response['Item']

	except ClientError as e:
		raise HTTPException(status_code=500, detail=f"Erro no DynamoDB: {e.response['Error']['Message']}")


@app.post("/api/{table_name}/item", summary="Proxy para PutItem/Write (Escrita Autorizada)")
async def put_item_proxy(
	table_name: str,
	request: DynamoDBRequest,
	# Chama a dependência para verificar permissão de 'write'
	authorized: bool = Depends(authorize_write) 
):
	"""
	Executa um PutItem (criação/sobrescrita) no DynamoDB APENAS se o usuário tiver permissão '{tabela}:write'.
	
	Args:
		table_name (str): Tabela alvo.
		request (DynamoDBRequest): Corpo da requisição contendo key e attributes.
	"""
	try:
		table = dynamodb.Table(table_name)
		
		# Combina a chave e os atributos
		item_to_put = request.key.copy()
		item_to_put.update(request.attributes)
		
		table.put_item(Item=item_to_put)
		return {"message": f"Item inserido/atualizado com sucesso na tabela {table_name}"}

	except ClientError as e:
		raise HTTPException(status_code=500, detail=f"Erro no DynamoDB: {e.response['Error']['Message']}")

@app.put("/api/{table_name}/item", summary="Proxy para PutItem/Update (Sobrescrita Autorizada)")
async def update_item_proxy(
	table_name: str,
	request: DynamoDBRequest,
	# Chama a dependência para verificar permissão de 'update'
	authorized: bool = Depends(authorize_update) 
):
	"""
	Executa um PutItem (sobrescrita total) no DynamoDB APENAS se o usuário tiver permissão '{tabela}:update'.
	
	Args:
		table_name (str): Tabela alvo.
		request (DynamoDBRequest): Corpo da requisição contendo key e attributes.
	"""
	try:
		table = dynamodb.Table(table_name)
		
		# Combina a chave e os atributos para sobrescrever o item
		item_to_put = request.key.copy()
		item_to_put.update(request.attributes)
		
		# Usa put_item para sobrescrever o item existente
		table.put_item(Item=item_to_put)
		return {"message": f"Item atualizado/sobrescrito com sucesso na tabela {table_name}"}

	except ClientError as e:
		raise HTTPException(status_code=500, detail=f"Erro no DynamoDB: {e.response['Error']['Message']}")

@app.delete("/api/{table_name}/item", summary="Proxy para DeleteItem/Delete (Deleção Autorizada)")
async def delete_item_proxy(
	table_name: str,
	key: str, 
	key_value: str,
	# Chama a dependência para verificar permissão de 'delete'
	authorized: bool = Depends(authorize_delete)
):
	"""
	Executa um DeleteItem no DynamoDB APENAS se o usuário tiver permissão '{tabela}:delete'.
	
	Args:
		table_name (str): Tabela alvo.
		key (str): Nome da chave primária a ser deletada.
		key_value (str): Valor da chave primária a ser deletada.
	"""
	try:
		table = dynamodb.Table(table_name)
		
		# DynamoDB deleta com base na chave principal
		Key = {key: key_value}
		table.delete_item(Key=Key)
		
		return {"message": f"Item deletado com sucesso da tabela {table_name}"}

	except ClientError as e:
		raise HTTPException(status_code=500, detail=f"Erro no DynamoDB: {e.response['Error']['Message']}")


