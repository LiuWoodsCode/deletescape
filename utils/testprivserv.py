from multiprocessing.connection import Client

conn = Client(("localhost", 6000), authkey=b"secret")

conn.send({"cmd": "ping"})
print(conn.recv())

conn.close()