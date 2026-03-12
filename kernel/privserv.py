from multiprocessing.connection import Listener

listener = Listener(address=("localhost", 6000), authkey=b"secret")

while True:
    conn = listener.accept()
    msg = conn.recv()
    print("received:", msg)

    conn.send({"status": "ok"})
    conn.close()