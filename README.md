# Azure Container Apps - OpenTelemetry + Application Insights Demo

This repository demonstrates a complete three-tier microservices application deployed on Azure Container Apps (ACA) with comprehensive OpenTelemetry instrumentation and Azure Application Insights integration.

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────┐
│               Azure Container Apps Environment             │
│                                                            │
│  ┌──────────────────┐      ┌──────────────────┐            │
│  │   Storefront     │────> │   Orders API     │            │
│  │   Frontend       │      │   (Port 8001)    │            │
│  │   (Port 8080)    │      │                  │            │
│  │   [External]     │      │   [Internal]     │            │
│  └──────────────────┘      └────────┬─────────┘            │
│                                     │                      │
│                                     ▼                      │
│                            ┌──────────────────┐            │
│                            │  Inventory API   │            │
│                            │   (Port 8000)    │            │
│                            │                  │            │
│                            │   [Internal]     │            │
│                            └──────────────────┘            │
│                                                            │
└────────────────────────────────────────────────────────────┘
                               │
                               ▼
                   ┌────────────────────────┐
                   │  Azure Application     │
                   │  Insights              │
                   │  (OpenTelemetry)       │
                   └────────────────────────┘
```

## 📦 Components

### 1. **Inventory API** (Python/FastAPI)
- Manages product inventory and stock levels
- Endpoints:
  - `GET /api/inventory` - List all inventory items
  - `GET /api/inventory/{product_id}` - Get specific product inventory
  - `POST /api/inventory/{product_id}/reserve` - Reserve inventory
- **Internal only** (not externally accessible)

### 2. **Orders API** (Python/FastAPI)
- Handles order creation and management
- Calls Inventory API to check stock and reserve products
- Endpoints:
  - `GET /api/orders` - List all orders
  - `GET /api/orders/{order_id}` - Get specific order
  - `POST /api/orders` - Create new order
- **Internal only** (not externally accessible)

### 3. **Storefront Frontend** (Python/FastAPI + HTML/JS)
- Web UI for customers to browse products and place orders
- Calls Orders API for all order operations
- Features:
  - Product catalog browsing
  - Shopping cart functionality
  - Order placement
  - Order history viewing
- **Externally accessible**

## 🔭 OpenTelemetry Integration

All three services are fully instrumented with OpenTelemetry:

### Tracing
- **Distributed tracing** across all services
- Automatic HTTP instrumentation for FastAPI and HTTPX
- Custom spans for business operations
- Trace propagation: Frontend → Orders API → Inventory API

### Metrics
- Custom metrics:
  - `inventory.checks` - Number of inventory checks
  - `inventory.stock_level` - Stock level changes
  - `orders.created` - Number of orders created
  - `orders.value` - Order values (histogram)
  - `frontend.page_views` - Page view counts
  - `frontend.order_requests` - Order requests from frontend

### Exporter
- Azure Monitor OpenTelemetry Exporter
- Sends traces and metrics to Application Insights
- Connection via `APPLICATIONINSIGHTS_CONNECTION_STRING` environment variable

## 🚀 Deployment

For complete setup instructions see the **[QUICKSTART.md](QUICKSTART.md)** guide.

