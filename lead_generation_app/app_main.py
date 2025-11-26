import os
import time
import logging
from lead_generation_app.database.database import init_db
from lead_generation_app.metrics import start_http_server
from lead_generation_app.webhooks import start_webhook_server


def main():
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    init_db()
    port = int(os.getenv("METRICS_PORT", "8000"))
    start_http_server(host="0.0.0.0", port=port)
    wport = int(os.getenv("WEBHOOK_PORT", "8080"))
    start_webhook_server(host="0.0.0.0", port=wport)
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
