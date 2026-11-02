import socket
import selectors
import time
import heapq
import os
import sys
import signal

# Configurações de endereço e porta
HOST = '127.0.0.1'  # 'localhost' (escuta apenas conexões locais)
PORT = 65432        # Portas acima de 1023 não exigem privilégios de administrador
dicionario = dict()
heap = []

sel = selectors.DefaultSelector()

COMANDOS = {
    'GET': (2,),
    'DEL': (2,),
    'SET': (3, 5),
}

def aplicar_comando(linha):
    parse = linha.split(" ")
    comando = parse[0]
    chave = parse[1]

    quando_expira = -1
    valor = " ".join(parse[2:])

    if len(parse) >= 4 and parse[-2].upper() in ("EX", "PXAT"):
        valor = " ".join(parse[2:-2])
        numero = int(parse[-1])
        if parse[-2].upper() == "EX":
            quando_expira = int(time.time() * 1000 + numero * 1000)
        else:
            quando_expira = numero

    if comando.upper() == 'SET':
        if quando_expira != -1:
            heapq.heappush(heap, (quando_expira, chave))
        dicionario[chave] = (valor, quando_expira)
        return quando_expira
    elif comando.upper() == 'DEL':
        try:
            dicionario.pop(chave)
            return True
        except KeyError:
            return False

def aceitar_conexao(server_socket):

    client_socket, endereco = server_socket.accept()
    print(f"[+] Conexão aceita de {endereco}")

    client_socket.setblocking(False)

    dado_extra = {"buffer": ""}
    sel.register(client_socket, selectors.EVENT_READ, dado_extra)


def atender_cliente(client_socket, dado_extra, arquivo_log):

    data = client_socket.recv(1024)

    if not data:
        print("[-] Cliente desconectou")
        sel.unregister(client_socket)
        client_socket.close()
        return

    dado_extra["buffer"] += data.decode('utf-8')

    while '\n' in dado_extra["buffer"]:
        linha, dado_extra["buffer"] = dado_extra["buffer"].split("\n", 1)

        try:
            parse = linha.split(" ")
            comando = parse[0].upper()

            if comando not in COMANDOS:
                resposta = f"ERR unknown command '{parse[0]}', with args beginning with: {' '.join(parse[1:])}\n"
            else:
                chave = parse[1]

                if len(parse) >= 2 and parse[-2].upper() == "EX":
                    valor = " ".join(parse[2:-2])
                else:
                    valor = " ".join(parse[2:])

                resposta = ""

                if comando.upper() == 'SET':
                    quando_expira = aplicar_comando(linha)
                    if quando_expira != -1:
                        arquivo_log.write(f'{comando} {chave} {valor} PXAT {quando_expira}\n')
                    else:
                        arquivo_log.write(f'{linha}\n')
                    arquivo_log.flush()
                    os.fsync(arquivo_log.fileno())
                    resposta = "OK\n"
                elif comando.upper() == 'GET':
                    valor, quando_expira = dicionario.get(chave, ("chave não existe", -1))
                    agora = time.time() * 1000
                    if quando_expira == -1 or agora <= quando_expira:
                        resposta = f"{valor}\n"
                    else:
                        dicionario.pop(chave)
                        resposta = f"a chave {chave} expirou\n"
                elif comando.upper() == 'DEL':
                    sucesso = aplicar_comando(linha)
                    if sucesso:
                        arquivo_log.write(f'{linha}\n')
                        arquivo_log.flush()
                        os.fsync(arquivo_log.fileno())
                        resposta = "OK\n"
                    else:
                        resposta = "chave não existe\n"
                
        except Exception as erro:
            print(f"[ERRO] {linha!r}: {erro!r}")
            resposta = "ERR\n"

        print(f"[Recebido]: {linha}")
                    
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
        