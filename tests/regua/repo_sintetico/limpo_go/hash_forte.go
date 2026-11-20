package main

import (
	"crypto/sha256"
	"encoding/hex"
)

func resumo(dados []byte) string {
	h := sha256.Sum256(dados)
	return hex.EncodeToString(h[:])
}
