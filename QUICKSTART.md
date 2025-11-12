# Quick Start Guide

## 🚀 Getting Started

### 1. Azure Setup

First, create the required Azure resources:

```bash
# Set your variables
LOCATION="eastus"
RG="rg-aca-otel-demo"
ACR_NAME="acrdemo$(openssl rand -hex 4)"
ACA_ENV="aca-env-otel-demo"
APP_INSIGHTS="appins-otel-demo"
WORKSPACE="workspace-otel-demo"

# Create resource group
az group create --name $RG --location $LOCATION

# Create Log Analytics workspace
az monitor log-analytics workspace create \
  --resource-group $RG \
  --workspace-name $WORKSPACE \
  --location $LOCATION

WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group $RG \
  --workspace-name $WORKSPACE \
  --query customerId \
  --output tsv)

WORKSPACE_SECRET=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group $RG \
  --workspace-name $WORKSPACE \
  --query primarySharedKey \
  --output tsv)

# Create Container Apps Environment
az containerapp env create \
  --name $ACA_ENV \
  --resource-group $RG \
  --location $LOCATION \
  --logs-workspace-id $WORKSPACE_ID \
  --logs-workspace-key $WORKSPACE_SECRET

# Create Container Registry
az acr create \
  --resource-group $RG \
  --name $ACR_NAME \
  --sku Basic

# Grant AcrPull permission to Container Apps Environment
# This allows Container Apps to pull images from ACR
ACA_ENV_IDENTITY=$(az containerapp env show \
  --name $ACA_ENV \
  --resource-group $RG \
  --query properties.appLogsConfiguration.logAnalyticsConfiguration.customerId \
  --output tsv)

# Get the Container Apps Environment's system-assigned identity
ACA_ENV_PRINCIPAL_ID=$(az containerapp env show \
  --name $ACA_ENV \
  --resource-group $RG \
  --query identity.principalId \
  --output tsv)

# If the environment doesn't have a managed identity, enable it
if [ -z "$ACA_ENV_PRINCIPAL_ID" ] || [ "$ACA_ENV_PRINCIPAL_ID" == "null" ]; then
    az containerapp env identity assign \
    --name "$ACA_ENV" \
    --resource-group "$RG" \
    --system-assigned

    # Leer el principalId del Environment
    ACA_ENV_PRINCIPAL_ID=$(az containerapp env identity show \
    --name "$ACA_ENV" \
    --resource-group "$RG" \
    --query 'principalId' \
    --output tsv)
fi

# Get ACR resource ID
ACR_ID=$(az acr show \
  --name $ACR_NAME \
  --resource-group $RG \
  --query id \
  --output tsv)

# Assign AcrPull role to the Container Apps Environment identity
az role assignment create \
  --assignee $ACA_ENV_PRINCIPAL_ID \
  --role AcrPull \
  --scope $ACR_ID

# Create Application Insights
az monitor app-insights component create \
  --app $APP_INSIGHTS \
  --location $LOCATION \
  --resource-group $RG \
  --workspace $WORKSPACE

# Get Application Insights Connection String
APP_INSIGHTS_CONN_STR=$(az monitor app-insights component show \
  --app $APP_INSIGHTS \
  --resource-group $RG \
  --query connectionString \
  --output tsv)

echo "ACR_NAME: $ACR_NAME"
echo "ACA_ENV: $ACA_ENV"
echo "RG: $RG"
echo "APP_INSIGHTS_CONN_STR: $APP_INSIGHTS_CONN_STR"
```

### 2. GitHub Secrets Setup

#### Configure Azure AD App with Federated Credentials (OIDC)

```bash
# Set variables
APP_NAME="sp-aca-otel-demo"
SUBS="YOUR_SUBSCRIPTION_ID"  # Replace with your subscription ID
SCOPE="/subscriptions/$SUBS/resourceGroups/$RG"
REPO_OWNER="YOUR_GITHUB_USERNAME"  # Replace with your GitHub username
REPO_NAME="aca-demo-monitoring"
SUBJECT="repo:${REPO_OWNER}/${REPO_NAME}:ref:refs/heads/main"

# Create App registration
APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
echo "Application (Client) ID: $APP_ID"

# Create Service principal
az ad sp create --id "$APP_ID"

# Assign Contributor role to the resource group
az role assignment create \
  --assignee "$APP_ID" \
  --role "Contributor" \
  --scope "$SCOPE"

# Create federated credential for GitHub Actions
az ad app federated-credential create \
  --id "$APP_ID" \
  --parameters '{
    "name": "github-main",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "'"$SUBJECT"'",
    "audiences": ["api://AzureADTokenExchange"]
  }'

# Get Tenant ID
TENANT_ID=$(az account show --query tenantId -o tsv)
echo "Tenant ID: $TENANT_ID"
echo "Subscription ID: $SUBS"
```

#### Add GitHub Secrets

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

1. **AZURE_CLIENT_ID**: `$APP_ID` (from above)
2. **AZURE_TENANT_ID**: `$TENANT_ID` (from above)
3. **AZURE_SUBSCRIPTION_ID**: `$SUBS` (your subscription ID)
4. **ACR_NAME**: `acrdemoXXXXXXXX` (from step 1)
5. **ACA_ENV_NAME**: `aca-env-otel-demo`
6. **ACA_RG**: `rg-aca-otel-demo`
7. **APPLICATIONINSIGHTS_CONNECTION_STRING**: Connection string from step 1

## 📊 Viewing Telemetry

### Application Map
1. Go to Azure Portal
2. Navigate to your Application Insights resource
3. Click "Application Map" in the left menu
4. You'll see: `storefront-frontend` → `orders-api` → `inventory-api`

### End-to-End Transactions
1. In Application Insights, click "Transaction search"
2. Set time range to last 30 minutes
3. Click on any request to see the full trace
4. You'll see spans from all three services

### Performance
1. Click "Performance" in Application Insights
2. Select "Dependencies" tab
3. You'll see response times for calls between services

### Custom Metrics
1. Click "Metrics" in Application Insights
2. Add metrics:
   - `inventory.checks` - Inventory check operations
   - `orders.created` - Number of orders created
   - `frontend.page_views` - Page views
   - `orders.value` - Order values

### Live Metrics
1. Click "Live Metrics" for real-time monitoring
2. Place orders in the frontend
3. Watch requests flow through the system in real-time

## 🧪 Testing Scenarios

### Scenario 1: Successful Order
1. Open the storefront
2. Add items to cart (laptop, mouse, keyboard)
3. Enter customer ID: `CUST001`
4. Click "Place Order"
5. Check Application Insights for the complete trace

### Scenario 2: Insufficient Stock
1. Try to order a large quantity (e.g., 200 laptops)
2. You'll get an error
3. Check Application Insights to see error tracking and the failed trace

### Scenario 3: View Application Map
1. Place several orders
2. Go to Application Map in App Insights
3. See the dependencies and call volumes

## 🔧 Local Development

To run services locally for testing:

```bash
# Terminal 1 - Inventory API
cd inventory-api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
export APPLICATIONINSIGHTS_CONNECTION_STRING="your-connection-string"
uvicorn app:app --host 0.0.0.0 --port 8000

# Terminal 2 - Orders API
cd orders-api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export APPLICATIONINSIGHTS_CONNECTION_STRING="your-connection-string"
export INVENTORY_API_URL="http://localhost:8000"
uvicorn app:app --host 0.0.0.0 --port 8001

# Terminal 3 - Storefront Frontend
cd storefront-frontend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export APPLICATIONINSIGHTS_CONNECTION_STRING="your-connection-string"
export ORDERS_API_URL="http://localhost:8001"
uvicorn app:app --host 0.0.0.0 --port 8080
```

Open http://localhost:8080 in your browser.
