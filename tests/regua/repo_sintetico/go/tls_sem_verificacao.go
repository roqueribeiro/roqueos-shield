package main

import (
	"crypto/tls"
	"net/http"
)

func cliente() *http.Client {
	return &http.Client{Transport: &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}}
}
