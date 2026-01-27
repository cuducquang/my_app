package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"strings"
	"time"
)

type Config struct {
	Port            string
	EurekaServerURL string
	AppName         string
	InstanceID      string
	PreferIP        bool

	// Flask discovery
	FlaskAppName  string
	FlaskBaseURL  string // fallback if Eureka has no instances
	RequestTimout time.Duration
}

func getenv(key, def string) string {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return def
	}
	return v
}

func localIP() string {
	// Best-effort: pick first non-loopback IPv4.
	ifaces, err := net.Interfaces()
	if err != nil {
		return "127.0.0.1"
	}
	for _, iface := range ifaces {
		if iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagLoopback != 0 {
			continue
		}
		addrs, _ := iface.Addrs()
		for _, a := range addrs {
			var ip net.IP
			switch v := a.(type) {
			case *net.IPNet:
				ip = v.IP
			case *net.IPAddr:
				ip = v.IP
			}
			if ip == nil {
				continue
			}
			ip = ip.To4()
			if ip == nil {
				continue
			}
			return ip.String()
		}
	}
	return "127.0.0.1"
}

func mustParseDuration(s string, def time.Duration) time.Duration {
	s = strings.TrimSpace(s)
	if s == "" {
		return def
	}
	d, err := time.ParseDuration(s)
	if err != nil {
		return def
	}
	return d
}

func loadConfig() Config {
	port := getenv("PORT", "8080")
	appName := getenv("APP_NAME", "API-GATEWAY")
	ip := localIP()
	instanceID := getenv("INSTANCE_ID", fmt.Sprintf("%s:%s:%s", strings.ToLower(appName), ip, port))

	return Config{
		Port:            port,
		EurekaServerURL: strings.TrimRight(getenv("EUREKA_SERVER_URL", "http://localhost:8761/eureka"), "/"),
		AppName:         appName,
		InstanceID:      instanceID,
		PreferIP:        strings.ToLower(getenv("PREFER_IP", "true")) == "true",
		FlaskAppName:    getenv("FLASK_APP_NAME", "FLASK-SERVICE"),
		FlaskBaseURL:    strings.TrimRight(getenv("FLASK_BASE_URL", ""), "/"),
		RequestTimout:   mustParseDuration(getenv("REQUEST_TIMEOUT", "10s"), 10*time.Second),
	}
}

type EurekaClient struct {
	baseURL string
	client  *http.Client
}

func NewEurekaClient(baseURL string, timeout time.Duration) *EurekaClient {
	return &EurekaClient{
		baseURL: strings.TrimRight(baseURL, "/"),
		client:  &http.Client{Timeout: timeout},
	}
}

func (e *EurekaClient) Register(ctx context.Context, cfg Config, ip string) error {
	// Eureka Server accepts XML reliably.
	// POST /eureka/apps/{APP}
	registerURL := fmt.Sprintf("%s/apps/%s", e.baseURL, strings.ToUpper(cfg.AppName))
	homePageURL := fmt.Sprintf("http://%s:%s/", ip, cfg.Port)
	statusPageURL := fmt.Sprintf("http://%s:%s/health", ip, cfg.Port)
	healthCheckURL := fmt.Sprintf("http://%s:%s/health", ip, cfg.Port)

	payload := fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<instance>
  <instanceId>%s</instanceId>
  <hostName>%s</hostName>
  <app>%s</app>
  <ipAddr>%s</ipAddr>
  <status>UP</status>
  <port enabled="true">%s</port>
  <securePort enabled="false">443</securePort>
  <homePageUrl>%s</homePageUrl>
  <statusPageUrl>%s</statusPageUrl>
  <healthCheckUrl>%s</healthCheckUrl>
  <dataCenterInfo class="com.netflix.appinfo.InstanceInfo$DefaultDataCenterInfo">
    <name>MyOwn</name>
  </dataCenterInfo>
</instance>`, cfg.InstanceID, ip, strings.ToUpper(cfg.AppName), ip, cfg.Port, homePageURL, statusPageURL, healthCheckURL)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, registerURL, strings.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/xml")
	resp, err := e.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 200 && resp.StatusCode <= 299 {
		return nil
	}
	b, _ := io.ReadAll(resp.Body)
	return fmt.Errorf("eureka register failed: %s: %s", resp.Status, string(b))
}

func (e *EurekaClient) Heartbeat(ctx context.Context, cfg Config) error {
	// PUT /eureka/apps/{APP}/{instanceId}
	u := fmt.Sprintf("%s/apps/%s/%s", e.baseURL, strings.ToUpper(cfg.AppName), cfg.InstanceID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, u, nil)
	if err != nil {
		return err
	}
	resp, err := e.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 200 && resp.StatusCode <= 299 {
		return nil
	}
	b, _ := io.ReadAll(resp.Body)
	return fmt.Errorf("eureka heartbeat failed: %s: %s", resp.Status, string(b))
}

type EurekaInstance struct {
	Status      string `json:"status"`
	HomePageURL string `json:"homePageUrl"`
	IPAddr      string `json:"ipAddr"`
	Port        struct {
		Value int `json:"$"`
	} `json:"port"`
}

type eurekaAppResponse struct {
	Application struct {
		Instance []EurekaInstance `json:"instance"`
	} `json:"application"`
}

func (e *EurekaClient) ResolveBaseURL(ctx context.Context, appName string) (string, error) {
	u := fmt.Sprintf("%s/apps/%s", e.baseURL, strings.ToUpper(appName))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Accept", "application/json")
	resp, err := e.client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("resolve app failed: %s: %s", resp.Status, string(b))
	}

	var data eurekaAppResponse
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return "", err
	}

	// Pick first UP instance, otherwise first instance.
	var chosen *EurekaInstance
	for i := range data.Application.Instance {
		inst := &data.Application.Instance[i]
		if strings.EqualFold(inst.Status, "UP") {
			chosen = inst
			break
		}
	}
	if chosen == nil && len(data.Application.Instance) > 0 {
		chosen = &data.Application.Instance[0]
	}
	if chosen == nil {
		return "", fmt.Errorf("no instances for %s", appName)
	}
	if chosen.HomePageURL != "" {
		return strings.TrimRight(chosen.HomePageURL, "/"), nil
	}
	if chosen.IPAddr != "" && chosen.Port.Value != 0 {
		return fmt.Sprintf("http://%s:%d", chosen.IPAddr, chosen.Port.Value), nil
	}
	return "", fmt.Errorf("instance missing url fields for %s", appName)
}

func proxyJSON(w http.ResponseWriter, r *http.Request, client *http.Client, method, url string, body []byte) {
	var bodyReader io.Reader
	if body != nil {
		bodyReader = bytes.NewReader(body)
	}
	req, err := http.NewRequestWithContext(r.Context(), method, url, bodyReader)
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
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok"}`))
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

	addr := ":" + cfg.Port
	log.Printf("api-gateway listening on %s (eureka=%s, flaskApp=%s)", addr, cfg.EurekaServerURL, cfg.FlaskAppName)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatal(err)
	}
}
