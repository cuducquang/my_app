import time
from typing import Optional

import requests

from app.config import AppConfig, local_ip
from app.utils.logging import get_logger


logger = get_logger()


def eureka_register(config: AppConfig) -> Optional[bool]:
    if not config.eureka_server_url:
        return None

    ip = local_ip()
    instance_id = config.eureka_instance_id
    app_name = config.eureka_app_name.upper()
    base = config.eureka_server_url
    if not base.endswith("/eureka"):
        base = base + "/eureka"

    register_url = f"{base}/apps/{app_name}"
    home = f"http://{ip}:{config.port}/"
    health = f"http://{ip}:{config.port}/health"

    payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<instance>
  <instanceId>{instance_id}</instanceId>
  <hostName>{ip}</hostName>
  <app>{app_name}</app>
  <ipAddr>{ip}</ipAddr>
  <status>UP</status>
  <port enabled="true">{config.port}</port>
  <securePort enabled="false">443</securePort>
  <homePageUrl>{home}</homePageUrl>
  <statusPageUrl>{health}</statusPageUrl>
  <healthCheckUrl>{health}</healthCheckUrl>
  <dataCenterInfo class="com.netflix.appinfo.InstanceInfo$DefaultDataCenterInfo">
    <name>MyOwn</name>
  </dataCenterInfo>
</instance>"""

    while True:
        try:
            res = requests.post(
                register_url,
                data=payload,
                headers={"Content-Type": "application/xml"},
                timeout=5,
            )
            if 200 <= res.status_code <= 299:
                logger.info("[eureka] registered %s (%s)", app_name, instance_id)
                break
            logger.warning("[eureka] register failed: %s %s", res.status_code, res.text)
        except Exception as exc:
            logger.warning("[eureka] register error: %s", exc)
        time.sleep(5)

    heartbeat_url = f"{base}/apps/{app_name}/{instance_id}"
    while True:
        try:
            res = requests.put(heartbeat_url, timeout=5)
            if res.status_code < 200 or res.status_code > 299:
                logger.warning("[eureka] heartbeat failed: %s %s", res.status_code, res.text)
        except Exception as exc:
            logger.warning("[eureka] heartbeat error: %s", exc)
        time.sleep(30)

