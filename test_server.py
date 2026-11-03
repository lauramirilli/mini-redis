from server import aplicar_comando, dicionario, heap, validar_set
import pytest

@pytest.fixture(autouse=True)
def limpar_estado():
    dicionario.clear()
    heap.clear()

def test_set_sem_ttl():
    aplicar_comando('SET nome Laura')
    assert dicionario['nome'] == ('Laura', -1)

def test_set_com_ttl():
    aplicar_comando('SET nome Laura EX 10')
    valor, quando_expira = dicionario['nome']
    assert valor == 'Laura'
    assert quando_expira != -1  # tem TTL, não é "sem expiração"

def test_del_chave_existe():
    aplicar_comando('SET nome Laura')
    apagados = aplicar_comando('DEL nome chaveinexistente')
    assert apagados > 0

def test_del_chave_inexistente():
    apagados = aplicar_comando('DEL nome')
    assert apagados == 0

def test_validar_set():
    linha = "SET a b EX -2"
    def parsear(linha):
        parse = linha.split(" ")
        return parse[1:]
    args = parsear(linha)
    
    assert validar_set(args) == "ERR invalid expire time in 'set' command\n"