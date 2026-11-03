import socket
import selectors
import time
import heapq
import os
import sys
import signal
import traceback

# Configurações de endereço e porta
HOST = '127.0.0.1'  # 'localhost' (escuta apenas conexões locais)
PORT = 65432        # Portas acima de 1023 não exigem privilégios de administrador
dicionario = dict()
heap = []

sel = selectors.DefaultSelector()

COMANDOS = {
    'GET': (1, 1),
    'DEL': (2, 1),
    'SET': (2, None),
}

def parsear(linha):
    parse = linha.split(" ")
    return parse[0].upper(), parse[1:]

def validar_set(args):
    if len(args) == 2:
        return None
    if len(args) != 4:
        return "ERR syntax error argumentos\n"
    
    opcao = args[2]
    if opcao.upper() not in ("EX", "PXAT"):
        return "ERR syntax error opcao errada\n"
    
    try:
        numero = int(args[3])
    except ValueError:
        return "ERR value is not an integer or out of range\n"

    if numero <= 0:
        return "ERR invalid expire time in 'set' command\n"
    
    return None

def aplicar_comando(linha):
    comando, args = parsear(linha)
    chave = args[0]
    quando_expira = -1

    if len(args) == 4:
        opcao = args[2].upper()
        numero = int(args[3])
        if opcao == "EX":
            quando_expira = int(time.time() * 1000 + numero * 1000)
        elif opcao == "PXAT":
            quando_expira = numero

    if comando == 'SET':
        valor = args[1]
        if quando_expira != -1:
            heapq.heappush(heap, (quando_expira, chave))
        dicionario[chave] = (valor, quando_expira)
        return quando_expira
    elif comando == 'DEL':
        try:
            dicionario.pop(chave)
            return True
        except KeyError:
            return False

def aceitar_conexao(server_socket):

    client_socket, endereco = server_socket.accept()
    print(f"[+] Conexão aceita de {endereco}")

    client_socket.setblocking(False)

    dado_extra = {"buffer": b""}
    sel.register(client_socket, selectors.EVENT_READ, dado_extra)


def atender_cliente(client_socket, dado_extra, arquivo_log):

    data = client_socket.recv(1024)

    if not data:
        print("[-] Cliente desconectou")
        sel.unregister(client_socket)
        client_socket.close()
        return

    dado_extra["buffer"] += data

    while b'\n' in dado_extra["buffer"]:
        linha_bytes, dado_extra["buffer"] = dado_extra["buffer"].split(b"\n", 1)

        try:
            linha = linha_bytes.decode('utf-8')
            comando, args = parsear(linha)

            if comando not in COMANDOS:
                resposta = f"ERR unknown command '{comando.lower()}', with args beginning with: {' '.join(args)}\n"

            elif len(args) < COMANDOS[comando][0] or (COMANDOS[comando][1] is not None and len(args) > COMANDOS[comando][1]):
                resposta = f"ERR wrong number of arguments for '{comando.lower()}' command\n"
            
            else:
                chave = args[0]
                resposta = ""

                if comando == 'SET':
                    erro = validar_set(args)
                    if erro:
                        resposta = erro
                    else:
                        quando_expira = aplicar_comando(linha)
                        valor = args[1]
                        if quando_expira != -1:
                            arquivo_log.write(f'{comando} {chave} {valor} PXAT {quando_expira}\n')
                        else:
                            arquivo_log.write(f'{linha}\n')
                        arquivo_log.flush()
                        os.fsync(arquivo_log.fileno())
                        resposta = "OK\n"
                elif comando == 'GET':
                    valor, quando_expira = dicionario.get(chave, ("chave não existe", -1))
                    agora = time.time() * 1000
                    if quando_expira == -1 or agora <= quando_expira:
                        resposta = f"{valor}\n"
                    else:
                        dicionario.pop(chave)
                        resposta = f"a chave {chave} expirou\n"
                elif comando == 'DEL':
                    sucesso = aplicar_comando(linha)
                    if sucesso:
                        arquivo_log.write(f'{linha}\n')
                        arquivo_log.flush()
                        os.fsync(arquivo_log.fileno())
                        resposta = "OK\n"
                    else:
                        resposta = "chave não existe\n"
                
        except Exception as erro:
            # print(f"[ERRO] {linha!r}: {erro!r}")
            # resposta = "ERR\n"
            traceback.print_exc()
            resposta = "ERR\n"

        print(f"[Recebido]: {linha_bytes!r}")
                    
        # Envia os dados de volta para o cliente (Echo)
        client_socket.sendall(resposta.encode('utf-8'))

def expirar_chaves():
    agora = time.time() * 1000
    while heap and heap[0][0] < agora:
        quando_expira_heap, chave_heap = heapq.heappop(heap)
        if chave_heap in dicionario and dicionario[chave_heap][1] == quando_expira_heap:
            dicionario.pop(chave_heap)

def tratar_sinal(signum, frame):
    print("\n[*] Sinal de encerramento recebido...")
    arquivo_log.close()
    sel.close()
    server_socket.close()
    sys.exit(0)

if __name__ == "__main__":
    arquivo_log = open('log.aof', 'a')

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen()
    server_socket.setblocking(False)

    sel.register(server_socket, selectors.EVENT_READ, None)

    signal.signal(signal.SIGINT, tratar_sinal)
    signal.signal(signal.SIGTERM, tratar_sinal)

    with open('log.aof', 'r') as log:
        for linha in log:
            linha = linha.strip()
            if not linha:
                continue
            aplicar_comando(linha)

    while True:
        eventos = sel.select(timeout=1)

        expirar_chaves()

        for key, mask in eventos:
            socket_pronto = key.fileobj
            dado_extra = key.data

            if dado_extra is None:
                aceitar_conexao(socket_pronto)
            else:
                atender_cliente(socket_pronto, dado_extra, arquivo_log)
        