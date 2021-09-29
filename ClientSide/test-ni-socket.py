import socket
import sys

# Connect the socket to the port where the server is listening
server_address = ('localhost', 7910)

# Create a TCP/IP socket
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(10)
    print('connecting to :', server_address)
    sock.connect(server_address)

    # Initializing 
    # Send initial response
    sock.sendall(b'Connected')

    amount_received = -1
    # Now waiting for basepath length message
    while amount_received < 5:
        data = sock.recv(5)
        amount_received += len(data)
        
