package main

import (
	"database/sql"
	"net/http"
)

var db *sql.DB

func buscar(w http.ResponseWriter, r *http.Request) {
	id := r.URL.Query().Get("id")
	rows, err := db.Query("SELECT nome FROM usuarios WHERE id = '" + id + "'")
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	defer rows.Close()
}
