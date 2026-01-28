package main

import (
	"context"
	"log"
	"net/http"
	"time"
)

func main() {
	cfg := loadConfig()

	httpClient := &http.Client{Timeout: cfg.RequestTimout}
	eureka := NewEurekaClient(cfg.EurekaServerURL, cfg.RequestTimout)
	ip := localIP()

	go func() {
		for {
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			err := eureka.Register(ctx, cfg, ip)
			cancel()
			if err == nil {
				break
			}
			log.Printf("[eureka] register failed: %v. Retrying in 5s...", err)
			time.Sleep(5 * time.Second)
		}
		log.Printf("[eureka] registered %s (%s)", cfg.AppName, cfg.InstanceID)

		t := time.NewTicker(30 * time.Second)
		defer t.Stop()
		for range t.C {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			if err := eureka.Heartbeat(ctx, cfg); err != nil {
				log.Printf("[eureka] heartbeat failed: %v", err)
			}
			cancel()
		}
	}()

	proxy := NewProxyClient(httpClient)
	rateLimiter := NewRateLimiter(100, 200) // 100 req/s, burst 200

	mux := http.NewServeMux()
	setupHandlers(mux, cfg, eureka, proxy, httpClient)

	// Chain middlewares: Logging -> RateLimit -> Mux
	handler := rateLimiter.Middleware(mux)
	handler = StructuredLoggingMiddleware(handler)

	addr := ":" + cfg.Port
	log.Printf("api-gateway listening on %s (eureka=%s, flaskApp=%s)", addr, cfg.EurekaServerURL, cfg.FlaskAppName)
	if err := http.ListenAndServe(addr, handler); err != nil {
		log.Fatal(err)
	}
}
