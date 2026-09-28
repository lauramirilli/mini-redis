import socket
import selectors

# Configurações de endereço e porta
HOST = '127.0.0.1'  # 'localhost' (escuta apenas conexões locais)
PORT = 65432        # Portas acima de 1023 não exigem privilégios de administrador
dicionario = dict()

sel = selectors.DefaultSelector()

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind((HOST, PORT))
server_socket.listen()
server_socket.setblocking(False)

sel.register(server_socket, selectors.EVENT_READ, None)


def aceitar_conexao(server_socket):

    client_socket, endereco = server_socket.accept()
    print(f"[+] Conexão aceita de {endereco}")

    client_socket.setblocking(False)

    dado_extra = {"buffer": ""}
    sel.register(client_socket, selectors.EVENT_READ, dado_extra)


def atender_cliente(client_socket, dado_extra):

    data = client_socket.recv(1024)

    if not data:
        print("[-] Cliente desconectou")
        sel.unregister(client_socket)
        client_socket.close()
        return

    dado_extra["buffer"] += data.decode('utf-8')

    if '\n' not in dado_extra["buffer"]:
        return
    else:
        linha, dado_extra["buffer"] = dado_extra["buffer"].split("\n", 1)
        
        parse = linha.split(" ")
        comando = parse[0]
        chave = parse[1]
        valor = " ".join(parse[2:])

        resposta = ""

        if comando.upper() == 'SET':
            dicionario[chave] = valor
            resposta = "OK\n"
        elif comando.upper() == 'GET':
            resultado = dicionario.get(chave, "chave não existe")
            resposta = f"{resultado}\n"
        elif comando.upper() == 'DEL':
            try:
                dicionario.pop(chave)
                resposta = "OK\n"
            except KeyError:
                resposta = "chave não existe\n"
            
        print(f"[Recebido]: {linha}")
        
        # Envia os dados de volta para o cliente (Echo)
        client_socket.sendall(resposta.encode('utf-8'))

try:
    while True:
        eventos = sel.select()

        for key, mask in eventos:
            socket_pronto = key.fileobj
            dado_extra = key.data

            if dado_extra is None:
                aceitar_conexao(socket_pronto)
            else:
                atender_cliente(socket_pronto, dado_extra)
except KeyboardInterrupt:
    print("\n[*] Encerrando servidor...")
finally:
    sel.close()
    server_socket.close()