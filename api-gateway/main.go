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

	// Best-effort registration (won't crash if Eureka not reachable).
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := eureka.Register(ctx, cfg, ip); err != nil {
			log.Printf("[eureka] register skipped/failed: %v", err)
			return
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

	mux := http.NewServeMux()
	setupHandlers(mux, cfg, eureka, httpClient)

	addr := ":" + cfg.Port
	log.Printf("api-gateway listening on %s (eureka=%s, flaskApp=%s)", addr, cfg.EurekaServerURL, cfg.FlaskAppName)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatal(err)
	}
}
