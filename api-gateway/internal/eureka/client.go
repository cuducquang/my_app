package eureka

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"my_app/api-gateway/internal/config"
)

// EurekaClient handles communication with Eureka service registry
type Client struct {
	baseURL string
	client  *http.Client
}

// NewEurekaClient creates a new Eureka client
func NewEurekaClient(baseURL string, timeout time.Duration) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		client:  &http.Client{Timeout: timeout},
	}
}

// Register registers this service instance with Eureka
func (e *Client) Register(ctx context.Context, cfg config.Config, ip string) error {
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

// Heartbeat sends a heartbeat to Eureka to renew the lease
func (e *Client) Heartbeat(ctx context.Context, cfg config.Config) error {
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

// EurekaInstance represents a service instance in Eureka
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

// ResolveBaseURL resolves the base URL of a service from Eureka
func (e *Client) ResolveBaseURL(ctx context.Context, appName string) (string, error) {
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
