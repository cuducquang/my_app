package main

import (
	"bytes"
	"io"
	"net/http"
)

// proxyJSON proxies a JSON request to another service
func proxyJSON(w http.ResponseWriter, r *http.Request, client *http.Client, method, url string, body []byte) {
	var bodyReader io.Reader
	if body != nil {
		bodyReader = bytes.NewReader(body)
	}
	req, err := http.NewRequest(method, url, bodyReader)
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	// Copy context from request
	req = req.WithContext(r.Context())
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	req.Header.Set("Accept", "application/json")
	if method == http.MethodPost {
		req.Header.Set("Content-Type", "application/json")
	}

	resp, err := client.Do(req)
	if err != nil {
		http.Error(w, err.Error(), 502)
		return
	}
	defer resp.Body.Close()

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}
