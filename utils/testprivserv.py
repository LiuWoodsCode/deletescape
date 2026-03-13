from multiprocessing.connection import Client


def call(address, endpoint, **data):

    conn = Client(address, authkey=b"secret")

    conn.send({
        "endpoint": endpoint,
        "data": data
    })

    r = conn.recv()
    conn.close()

    return r


print(call(("localhost", 9150), "kernel.uname"))
