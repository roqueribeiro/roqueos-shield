package main

import (
	"crypto/md5"
	"encoding/hex"
)

func senhaHash(senha string) string {
	h := md5.Sum([]byte(senha))
	return hex.EncodeToString(h[:])
}
