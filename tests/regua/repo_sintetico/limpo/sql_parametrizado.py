def usuario(conn, uid):
    return conn.execute("SELECT * FROM users WHERE id = ?", (uid,))
