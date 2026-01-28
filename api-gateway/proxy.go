package main

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/sony/gobreaker"
)

// ProxyClient handles proxied requests with Circuit Breaker
type ProxyClient struct {
	client *http.Client
	cb     *gobreaker.CircuitBreaker
}

// NewProxyClient creates a new ProxyClient with default Circuit Breaker settings
func NewProxyClient(client *http.Client) *ProxyClient {
	st := gobreaker.Settings{
		Name:        "API Gateway Proxy",
		MaxRequests: 1,                // Max requests allowed in half-open state
		Interval:    10 * time.Second, // Cyclic period of the closed state
		Timeout:     30 * time.Second, // Duration of open state
		ReadyToTrip: func(counts gobreaker.Counts) bool {
			// Trip if 3+ consecutive failures occur
			return counts.ConsecutiveFailures >= 3
		},
	}
	return &ProxyClient{
		client: client,
		cb:     gobreaker.NewCircuitBreaker(st),
	}
}

// ProxyJSON proxies a JSON request to another service protected by Circuit Breaker
func (p *ProxyClient) ProxyJSON(w http.ResponseWriter, r *http.Request, method, url string, body []byte) {
	var bodyReader io.Reader
	if body != nil {
		bodyReader = bytes.NewReader(body)
	}

	// Prepare request
	req, err := http.NewRequest(method, url, bodyReader)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	req = req.WithContext(r.Context())
	req.Header.Set("Accept", "application/json")
	if method == http.MethodPost {
		req.Header.Set("Content-Type", "application/json")
	}

	// Execute via Circuit Breaker
	result, err := p.cb.Execute(func() (interface{}, error) {
		resp, err := p.client.Do(req)
		if err != nil {
			return nil, err
		}
		// Treat 5xx as failures for the circuit breaker
		if resp.StatusCode >= 500 {
			// We return resp even on error so we can read body/headers if needed,
			// but we wrap it in error to trigger the CB failure counter.
			return resp, fmt.Errorf("upstream error: %d", resp.StatusCode)
		}
		return resp, nil
	})

	// Handle Circuit Breaker specific errors
	if err == gobreaker.ErrOpenState {
		http.Error(w, "Service Unavailable (Circuit Breaker Open)", http.StatusServiceUnavailable)
		return
	} else if err == gobreaker.ErrTooManyRequests {
		http.Error(w, "Service Unavailable (Circuit Breaker Half-Open Limit)", http.StatusServiceUnavailable)
		return
	}

	// If result is nil but err is set (network error), handle it
	if result == nil && err != nil {
		http.Error(w, fmt.Sprintf("Upstream failed: %v", err), http.StatusBadGateway)
		return
	}

	// If we got here, result is either a success response or a 5xx response (wrapped in error above)
	// We need to unwrap if it was returned as result
	resp, ok := result.(*http.Response)
	if !ok {
		// Should not happen if logic matches above
		http.Error(w, "Internal Proxy Error", http.StatusInternalServerError)
		return
	}
	defer resp.Body.Close()

	// Forward response
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}
