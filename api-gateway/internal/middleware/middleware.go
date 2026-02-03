package middleware

import (
	"encoding/json"
	"log"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"golang.org/x/time/rate"
)

// --- Logging Middleware ---

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (rec *statusRecorder) WriteHeader(code int) {
	rec.status = code
	rec.ResponseWriter.WriteHeader(code)
}

// StructuredLoggingMiddleware logs requests in JSON format
func StructuredLoggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)

		duration := time.Since(start)

		logEntry := map[string]interface{}{
			"level":       "info",
			"ts":          start.Format(time.RFC3339),
			"method":      r.Method,
			"path":        r.URL.Path,
			"remote_addr": r.RemoteAddr,
			"status":      rec.status,
			"duration_ms": duration.Milliseconds(),
			"user_agent":  r.UserAgent(),
		}

		// Use standard log, but format as JSON
		jsonBytes, _ := json.Marshal(logEntry)
		log.Println(string(jsonBytes))
	})
}

// --- Rate Limiting Middleware ---

// RateLimiter manages rate limits per IP
type RateLimiter struct {
	ips map[string]*rate.Limiter
	mu  sync.Mutex
	r   rate.Limit
	b   int
}

// NewRateLimiter creates a custom rate limiter
// r: limit (events/second)
// b: burst
func NewRateLimiter(r rate.Limit, b int) *RateLimiter {
	// In a real app run a background goroutine to clean up old IPs
	return &RateLimiter{
		ips: make(map[string]*rate.Limiter),
		r:   r,
		b:   b,
	}
}

func (l *RateLimiter) getLimiter(ip string) *rate.Limiter {
	l.mu.Lock()
	defer l.mu.Unlock()

	limiter, exists := l.ips[ip]
	if !exists {
		limiter = rate.NewLimiter(l.r, l.b)
		l.ips[ip] = limiter
	}
	return limiter
}

// Middleware applies rate limiting based on IP
func (l *RateLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ip := getIP(r)
		limiter := l.getLimiter(ip)
		if !limiter.Allow() {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			json.NewEncoder(w).Encode(map[string]string{
				"error": "Too Many Requests",
			})
			return
		}
		next.ServeHTTP(w, r)
	})
}

// getIP extracts the client IP, preferring X-Forwarded-For if available
func getIP(r *http.Request) string {
	xfwd := r.Header.Get("X-Forwarded-For")
	if xfwd != "" {
		// X-Forwarded-For: client, proxy1, proxy2
		ips := strings.Split(xfwd, ",")
		return strings.TrimSpace(ips[0])
	}
	ip, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return ip
}
