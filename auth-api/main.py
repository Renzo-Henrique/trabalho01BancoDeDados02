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
users_table = dynamodb.Table('users')
roles_table = dynamodb.Table('roles')

app = FastAPI(title="DynamoDB Auth Proxy API")

# --- 2. CONFIGURAÇÃO JWT ---
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "seu-segredo-super-secreto")
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login") # Endpoint de login

def create_access_token(data: dict):
	""" Cria um token JWT contendo os dados do usuário. """
	to_encode = data.copy()
	return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- 3. MODELOS Pydantic (Para validação de dados) ---
class UserLogin(BaseModel):
	username: str
	password: str # Lembrete: senhas em texto puro!

class UserToken(BaseModel):
	username: str
	role_name: str

class DynamoDBRequest(BaseModel):
	# Campos que você precisaria para PutItem, UpdateItem, etc.
	key: dict
	attributes: dict = {}
    
# --- 4. LÓGICA DE AUTORIZAÇÃO ---

async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserToken:
	""" Decodifica e valida o JWT para extrair o usuário e o papel. """
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
		# --- CORREÇÃO AQUI: Garante que role_name é uma string única ---
		role_name: str
		if isinstance(role_data, list) and role_data:
			role_name = role_data[0] # Pega o primeiro papel se for lista
		elif isinstance(role_data, str):
			role_name = role_data
		else:
			raise credentials_exception # Não encontrou um papel válido

		if username is None:
			raise credentials_exception
			
		return UserToken(username=username, role_name=role_name)
	except JWTError:
		raise credentials_exception

async def check_permission(
	user: UserToken = Depends(get_current_user), 
	table_name: str = "default", 
	action: str = "read"
):
	""" Verifica se o papel do usuário tem permissão para a ação na tabela. """
	permission_string = f"{table_name}:{action}"
	role_name = user.role_name

	# 1. Busca as permissões do papel
	try:
		response = roles_table.get_item(Key={'role_name': role_name})
		role_item = response.get('Item')

		if not role_item:
			raise HTTPException(status_code=403, detail=f"Papel '{role_name}' não encontrado.")

		# Como usamos boto3.resource, ele já deserializa para uma lista Python
		permissions = role_item.get('permissions', [])

		if not isinstance(permissions, list):
			# Se a permissão não for uma lista (ou se a estrutura estiver errada), forçamos uma lista vazia
			#print(f"Aviso: Permissão do papel {role_name} não é uma lista: {permissions}")
			permissions = []

		# 2. Verifica a permissão (Coringa ou Permissão Específica)
		if "*" in permissions or permission_string in permissions:
			return True
		# 3. Não Autorizado
		raise HTTPException(
			status_code=403,
			detail=f"Usuário não autorizado: Necessária permissão '{permission_string}'."
		)
		
		return False

	except ClientError as e:
		print(f"Erro ao buscar permissões: {e}")
		raise HTTPException(status_code=500, detail="Erro interno de autorização.")

# --- 5. ENDPOINTS DE AUTENTICAÇÃO E TESTE ---

@app.post("/login", summary="Autenticação e Geração de Token JWT")
async def login_for_access_token(form_data: UserLogin):
	"""
	Verifica as credenciais do usuário na tabela 'users' e retorna um JWT.
	"""
	try:
		response = users_table.get_item(Key={'username': form_data.username})
		user_item = response.get('Item')

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
		print(f"Erro no DynamoDB durante o login: {e}")
		raise HTTPException(status_code=500, detail="Erro no serviço de autenticação.")

@app.get("/users/me", summary="Testa o Token e Retorna Informações do Usuário")
async def read_users_me(current_user: UserToken = Depends(get_current_user)):
	return {"username": current_user.username, "role": current_user.role_name}

# --- 6. ENDPOINTS DE PROXY DO DYNAMODB (COM AUTORIZAÇÃO) ---

# Função Auxiliar de Autorização
async def authorize_read(table_name: str, current_user: UserToken = Depends(get_current_user)):
	""" Dependência para verificar permissão de 'read' em uma tabela específica. """
	return await check_permission(user=current_user, table_name=table_name, action="read")
	#return True # Retorna True se a permissão for concedida

async def authorize_write(table_name: str, current_user: UserToken = Depends(get_current_user)):
	""" Dependência para verificar permissão de 'write' em uma tabela específica. """
	return await check_permission(user=current_user, table_name=table_name, action="write")
	#return True # Retorna True se a permissão for concedida

async def authorize_delete(table_name: str, current_user: UserToken = Depends(get_current_user)):
	""" Dependência para verificar permissão de 'delete' em uma tabela específica. """
	return await check_permission(user=current_user, table_name=table_name, action="delete")
	#return True # Retorna True se a permissão for concedida

async def authorize_update(table_name: str, current_user: UserToken = Depends(get_current_user)):
	""" Dependência para verificar permissão de 'update' em uma tabela específica. """
	return await check_permission(user=current_user, table_name=table_name, action="update")
	#return True # Retorna True se a permissão for concedida


@app.get("/api/{table_name}/item", summary="Proxy para GetItem/Read (Consulta Autorizada)")
async def get_item_proxy(
	table_name: str, 
	key: str, 
	key_value: str,
	# A dependência agora chama a função auxiliar (authorize_read)
	authorized: bool = Depends(authorize_read) 
):
	"""
	Executa um GetItem APENAS se o usuário tiver permissão 'tabela:read'.
	"""
	try:
		# Note: A função 'authorize_read' já usou 'table_name' internamente.
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
	# A dependência agora chama a função auxiliar (authorize_write)
	authorized: bool = Depends(authorize_write) 
):
	"""
	Executa um PutItem APENAS se o usuário tiver permissão 'tabela:write'.
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

# --- NOVOS ENDPOINTS DE PROXY (UPDATE e DELETE) ---

@app.put("/api/{table_name}/item", summary="Proxy para PutItem/Update (Sobrescrita Autorizada)")
async def update_item_proxy(
    table_name: str,
    request: DynamoDBRequest, # Usa o mesmo modelo de request do POST
    # A dependência agora chama a função auxiliar (authorize_update)
    authorized: bool = Depends(authorize_update) 
):
    """
    Executa um PutItem (sobrescrita total) APENAS se o usuário tiver permissão 'tabela:update'.
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
    key: str = Query(..., description="Nome da chave primária (ex: customer_name)"), 
    key_value: str = Query(..., description="Valor da chave primária (ex: Alice)"),
    # A dependência agora chama a função auxiliar (authorize_delete)
    authorized: bool = Depends(authorize_delete)
):
    """
    Executa um DeleteItem APENAS se o usuário tiver permissão 'tabela:delete'.
    """
    try:
        table = dynamodb.Table(table_name)
        
        # DynamoDB deleta com base na chave principal
        Key = {key: key_value}
        table.delete_item(Key=Key)
        
        return {"message": f"Item deletado com sucesso da tabela {table_name}"}

    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Erro no DynamoDB: {e.response['Error']['Message']}")


