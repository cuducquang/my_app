package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"time"
)

// setupHandlers registers all HTTP handlers
func setupHandlers(mux *http.ServeMux, cfg Config, eureka *EurekaClient, httpClient *http.Client) {
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
				"health":     "/health",
				"swagger-ui": "/swagger-ui",
				"openapi":    "/openapi.json",
				"aggregate":  "/api-docs/aggregate",
				"flask":      "/flask",
				"flask-test": "/flask/test-infrastructure",
			},
		}
		json.NewEncoder(w).Encode(info)
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
    "/flask": {
      "get": {
        "summary": "Get Flask service status",
        "responses": {"200": {"description": "OK"}}
      }
    },
    "/flask/test-infrastructure": {
      "post": {
        "summary": "Test infrastructure",
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

		// 2. Try to fetch Flask service spec via Eureka
		flaskBase := cfg.FlaskBaseURL
		if u, err := eureka.ResolveBaseURL(ctx, cfg.FlaskAppName); err == nil {
			flaskBase = u
		}

		if flaskBase != "" {
			// Fetch Flask's OpenAPI spec to verify it exists
			flaskSpecURL := strings.TrimRight(flaskBase, "/") + "/openapi.json"
			req, err := http.NewRequestWithContext(ctx, http.MethodGet, flaskSpecURL, nil)
			if err == nil {
				req.Header.Set("Accept", "application/json")
				resp, err := httpClient.Do(req)
				if err == nil && resp.StatusCode == 200 {
					var flaskSpec interface{}
					if err := json.NewDecoder(resp.Body).Decode(&flaskSpec); err == nil {
						// Use proxy URL instead of direct URL to avoid CORS issues
						specs = append(specs, serviceSpec{
							Name: "flask-service",
							Spec: flaskSpec,
							URL:  "/api-docs/flask/openapi.json", // Proxy endpoint, not direct URL
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

	// Proxy endpoint for Flask's OpenAPI spec (to avoid CORS issues)
	mux.HandleFunc("/api-docs/flask/openapi.json", func(w http.ResponseWriter, r *http.Request) {
		base := cfg.FlaskBaseURL
		ctx, cancel := context.WithTimeout(r.Context(), cfg.RequestTimout)
		defer cancel()
		if u, err := eureka.ResolveBaseURL(ctx, cfg.FlaskAppName); err == nil {
			base = u
		}
		if base == "" {
			http.Error(w, "flask service not available", 503)
			return
		}

		// Fetch Flask's OpenAPI spec and proxy it
		flaskSpecURL := strings.TrimRight(base, "/") + "/openapi.json"
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, flaskSpecURL, nil)
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
		_, _ = w.Write([]byte(getSwaggerUIHTML()))
	})

	// Proxy: GET /flask -> Flask GET /
	mux.HandleFunc("/flask", func(w http.ResponseWriter, r *http.Request) {
		base := cfg.FlaskBaseURL
		ctx, cancel := context.WithTimeout(r.Context(), cfg.RequestTimout)
		defer cancel()
		if u, err := eureka.ResolveBaseURL(ctx, cfg.FlaskAppName); err == nil {
			base = u
		}
		if base == "" {
			http.Error(w, "no flask base url (set FLASK_BASE_URL or register FLASK_APP_NAME in Eureka)", 500)
			return
		}
		proxyJSON(w, r, httpClient, http.MethodGet, base+"/", nil)
	})

	// Proxy: POST /flask/test-infrastructure -> Flask POST /test-infrastructure
	mux.HandleFunc("/flask/test-infrastructure", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", 405)
			return
		}
		base := cfg.FlaskBaseURL
		ctx, cancel := context.WithTimeout(r.Context(), cfg.RequestTimout)
		defer cancel()
		if u, err := eureka.ResolveBaseURL(ctx, cfg.FlaskAppName); err == nil {
			base = u
		}
		if base == "" {
			http.Error(w, "no flask base url (set FLASK_BASE_URL or register FLASK_APP_NAME in Eureka)", 500)
			return
		}
		// Forward incoming JSON body if any; otherwise send empty object.
		body, _ := io.ReadAll(r.Body)
		if len(bytes.TrimSpace(body)) == 0 {
			body = []byte(`{}`)
		}
		proxyJSON(w, r, httpClient, http.MethodPost, base+"/test-infrastructure", body)
	})
}
