package server

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"time"

	"my_app/api-gateway/internal/config"
	"my_app/api-gateway/internal/eureka"
	"my_app/api-gateway/internal/proxy"
	"my_app/api-gateway/internal/swagger"
)

// NewMux registers all HTTP handlers.
func NewMux(cfg config.Config, eureka *eureka.Client, proxyClient *proxy.Client, httpClient *http.Client) *http.ServeMux {
	mux := http.NewServeMux()
	// Root path - show service info
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		info := map[string]interface{}{
			"service": "API Gateway",
			"version": "1.0.0",
			"status":  "running",
			"endpoints": map[string]string{
				"health":          "/health",
				"swagger-ui":      "/swagger-ui",
				"openapi":         "/openapi.json",
				"aggregate":       "/api-docs/aggregate",
				"agent":           "/agent",
				"agent-stream":    "/agent/stream",
				"circuit-breaker": "/admin/circuit-breaker",
			},
		}
		json.NewEncoder(w).Encode(info)
	})

	// Circuit Breaker Status
	mux.HandleFunc("/admin/circuit-breaker", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		counts := proxyClient.Counts()
		status := map[string]interface{}{
			"state": proxyClient.State().String(),
			"counts": map[string]interface{}{
				"requests":              counts.Requests,
				"total_successes":       counts.TotalSuccesses,
				"total_failures":        counts.TotalFailures,
				"consecutive_successes": counts.ConsecutiveSuccesses,
				"consecutive_failures":  counts.ConsecutiveFailures,
			},
		}
		json.NewEncoder(w).Encode(status)
	})

	// Health check
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})

	// OpenAPI spec for API Gateway
	mux.HandleFunc("/openapi.json", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
	spec := `{
  "openapi": "3.0.0",
  "info": {
    "title": "API Gateway",
    "description": "API Gateway for MLOps Platform",
    "version": "1.0.0"
  },
  "paths": {
    "/health": {
      "get": {
        "summary": "Health check",
        "responses": {"200": {"description": "OK"}}
      }
    },
    "/agent": {
      "post": {
        "summary": "Get agent recommendations",
        "responses": {"200": {"description": "OK"}}
      }
    },
    "/agent/stream": {
      "post": {
        "summary": "Stream agent recommendations",
        "responses": {"200": {"description": "OK"}}
      }
    }
  }
}`
		_, _ = w.Write([]byte(spec))
	})

	// Aggregation endpoint: collect OpenAPI specs from all services
	mux.HandleFunc("/api-docs/aggregate", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		type serviceSpec struct {
			Name string      `json:"name"`
			Spec interface{} `json:"spec"`
			URL  string      `json:"url,omitempty"`
		}

		var specs []serviceSpec

		// 1. Add API Gateway's own spec
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()

		specs = append(specs, serviceSpec{
			Name: "api-gateway",
			URL:  "/openapi.json",
		})

		// 2. Try to fetch Agent service spec via Eureka
		agentBase := cfg.AgentBaseURL
		if u, err := eureka.ResolveBaseURL(ctx, cfg.AgentAppName); err == nil {
			agentBase = u
		}

		if agentBase != "" {
			// Fetch Agent's OpenAPI spec to verify it exists
			agentSpecURL := strings.TrimRight(agentBase, "/") + "/openapi.json"
			req, err := http.NewRequestWithContext(ctx, http.MethodGet, agentSpecURL, nil)
			if err == nil {
				req.Header.Set("Accept", "application/json")
				resp, err := httpClient.Do(req)
				if err == nil && resp.StatusCode == 200 {
					var agentSpec interface{}
					if err := json.NewDecoder(resp.Body).Decode(&agentSpec); err == nil {
						// Use proxy URL instead of direct URL to avoid CORS issues
						specs = append(specs, serviceSpec{
							Name: "agent-service",
							Spec: agentSpec,
							URL:  "/api-docs/agent/openapi.json", // Proxy endpoint, not direct URL
						})
					}
					resp.Body.Close()
				}
			}
		}

		// Return aggregated response
		result := map[string]interface{}{
			"services": specs,
			"count":    len(specs),
		}
		json.NewEncoder(w).Encode(result)
	})

	// Proxy endpoint for Agent's OpenAPI spec (to avoid CORS issues)
	mux.HandleFunc("/api-docs/agent/openapi.json", func(w http.ResponseWriter, r *http.Request) {
		base := cfg.AgentBaseURL
		ctx, cancel := context.WithTimeout(r.Context(), cfg.RequestTimeout)
		defer cancel()
		if u, err := eureka.ResolveBaseURL(ctx, cfg.AgentAppName); err == nil {
			base = u
		}
		if base == "" {
			http.Error(w, "agent service not available", 503)
			return
		}

		// Fetch Agent's OpenAPI spec and proxy it
		agentSpecURL := strings.TrimRight(base, "/") + "/openapi.json"
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, agentSpecURL, nil)
		if err != nil {
			http.Error(w, err.Error(), 500)
			return
		}
		req.Header.Set("Accept", "application/json")
		resp, err := httpClient.Do(req)
		if err != nil {
			http.Error(w, err.Error(), 502)
			return
		}
		defer resp.Body.Close()

		// Copy headers
		for k, v := range resp.Header {
			if k != "Content-Length" {
				w.Header()[k] = v
			}
		}
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.WriteHeader(resp.StatusCode)
		_, _ = io.Copy(w, resp.Body)
	})

	// Swagger UI endpoint
	mux.HandleFunc("/swagger-ui", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte(swagger.GetUIHTML()))
	})

	// Proxy: POST /agent -> Agent-service POST /recommendations
	mux.HandleFunc("/agent", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", 405)
			return
		}
		base := cfg.AgentBaseURL
		ctx, cancel := context.WithTimeout(r.Context(), cfg.RequestTimeout)
		defer cancel()
		if u, err := eureka.ResolveBaseURL(ctx, cfg.AgentAppName); err == nil {
			base = u
		}
		if base == "" {
			http.Error(w, "no agent service base url", 500)
			return
		}
		body, _ := io.ReadAll(r.Body)
		if len(bytes.TrimSpace(body)) == 0 {
			body = []byte(`{}`)
		}
		proxyClient.ProxyJSON(w, r, http.MethodPost, base+"/recommendations", body)
	})

	// Proxy: POST /agent/stream -> Agent-service POST /recommendations/stream
	mux.HandleFunc("/agent/stream", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", 405)
			return
		}
		base := cfg.AgentBaseURL
		ctx, cancel := context.WithTimeout(r.Context(), cfg.RequestTimeout)
		defer cancel()
		if u, err := eureka.ResolveBaseURL(ctx, cfg.AgentAppName); err == nil {
			base = u
		}
		if base == "" {
			http.Error(w, "no agent service base url", 500)
			return
		}
		body, _ := io.ReadAll(r.Body)
		if len(bytes.TrimSpace(body)) == 0 {
			body = []byte(`{}`)
		}
		proxyClient.ProxyStream(w, r, http.MethodPost, base+"/recommendations/stream", body)
	})

	return mux
}
