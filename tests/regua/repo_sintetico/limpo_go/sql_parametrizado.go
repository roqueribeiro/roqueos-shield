package main

import "database/sql"

func buscar(db *sql.DB, id string) (*sql.Rows, error) {
	return db.Query("SELECT nome FROM usuarios WHERE id = $1", id)
}
