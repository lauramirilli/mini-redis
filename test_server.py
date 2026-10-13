from server import aplicar_comando, dicionario, heap
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
    assert aplicar_comando('DEL nome') == True

def test_del_chave_inexistente():
    assert aplicar_comando('DEL nome') == False