package main

import (
	"context"
	"log"
	"net/http"
	"time"

	"my_app/api-gateway/internal/config"
	"my_app/api-gateway/internal/eureka"
	"my_app/api-gateway/internal/middleware"
	"my_app/api-gateway/internal/proxy"
	"my_app/api-gateway/internal/server"
)

func main() {
	cfg := config.Load()

	httpClient := &http.Client{Timeout: cfg.RequestTimeout}
	eurekaClient := eureka.NewEurekaClient(cfg.EurekaServerURL, cfg.RequestTimeout)
	ip := config.LocalIP()

	go func() {
		for {
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			err := eurekaClient.Register(ctx, cfg, ip)
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
			if err := eurekaClient.Heartbeat(ctx, cfg); err != nil {
				log.Printf("[eureka] heartbeat failed: %v", err)
			}
			cancel()
		}
	}()

	proxyClient := proxy.New(httpClient)
	rateLimiter := middleware.NewRateLimiter(100, 200) // 100 req/s, burst 200

	mux := server.NewMux(cfg, eurekaClient, proxyClient, httpClient)

	// Chain middlewares: Logging -> RateLimit -> Mux
	handler := rateLimiter.Middleware(mux)
	handler = middleware.StructuredLoggingMiddleware(handler)

	addr := ":" + cfg.Port
	log.Printf("api-gateway listening on %s (eureka=%s, agentApp=%s)", addr, cfg.EurekaServerURL, cfg.AgentAppName)
	if err := http.ListenAndServe(addr, handler); err != nil {
		log.Fatal(err)
	}
}
