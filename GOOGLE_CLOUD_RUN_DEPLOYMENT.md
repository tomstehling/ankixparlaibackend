# Google Cloud Run Deployment Guide for AnkiXParlaI Backend

This guide will help you deploy the AnkiXParlaI backend to Google Cloud Run.

## 📋 Prerequisites

1. **Google Cloud SDK installed** and authenticated
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

2. **Docker installed** on your machine

3. **Environment variables ready** for your application

## 🚀 Deployment Steps

### 1. Set Environment Variables

Create a file `gcloud_env.txt` with your environment variables:

```bash
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL_NAME=openai/gpt-oss-20b
AUTH_MASTER_KEY=your_auth_master_key
DATABASE_URL_PROD=your_supabase_database_url
CONNECT_LOCALLY_TO_SUPABASE=false
```

**Important:** Replace the placeholder values with your actual credentials.

### 2. Build and Push Docker Image

```bash
# Set your Google Cloud project
export PROJECT_ID=your-project-id
export REGION=us-central1  # or your preferred region
export SERVICE_NAME=ankixparlai-backend
export IMAGE_NAME=ankixparlai-backend

# Build the Docker image
docker build -t gcr.io/$PROJECT_ID/$IMAGE_NAME .

# Tag the image
docker tag gcr.io/$PROJECT_ID/$IMAGE_NAME gcr.io/$PROJECT_ID/$IMAGE_NAME:latest

# Push to Google Container Registry
docker push gcr.io/$PROJECT_ID/$IMAGE_NAME:latest
```

### 3. Deploy to Cloud Run

```bash
# Deploy the service
gcloud run deploy $SERVICE_NAME \
  --image=gcr.io/$PROJECT_ID/$IMAGE_NAME:latest \
  --platform=managed \
  --region=$REGION \
  --allow-unauthenticated \
  --port=8080 \
  --memory=2Gi \
  --cpu=2 \
  --timeout=3600 \
  --env-vars-file=gcloud_env.txt
```

### 4. Alternative: Deploy using Google Cloud Build

If you want to use Google Cloud Build instead:

```bash
# Create a cloudbuild.yaml file
cat > cloudbuild.yaml << 'EOF'
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/$IMAGE_NAME:latest', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/$IMAGE_NAME:latest']
  - name: 'gcr.io/cloud-builders/gcloud'
    args:
      - 'run'
      - 'deploy'
      - '$SERVICE_NAME'
      - '--image=gcr.io/$PROJECT_ID/$IMAGE_NAME:latest'
      - '--platform=managed'
      - '--region=$REGION'
      - '--allow-unauthenticated'
      - '--port=8080'
      - '--memory=2Gi'
      - '--cpu=2'
      - '--timeout=3600'
timeout: '1600s'
images:
  - 'gcr.io/$PROJECT_ID/$IMAGE_NAME:latest'
EOF

# Trigger the build and deployment
gcloud builds submit --config cloudbuild.yaml
```

## 🔧 Configuration Details

### Port Configuration
- **Application Port:** 8080 (as specified in Dockerfile)
- **Cloud Run Port:** 8080
- **Environment Variable:** PORT=8080 (set by Cloud Run automatically)

### Resource Allocation
- **Memory:** 2GB (sufficient for LLM processing)
- **CPU:** 2 cores
- **Timeout:** 3600 seconds (1 hour)
- **Concurrency:** 80 (default for Cloud Run)

## 🔍 Troubleshooting

### Container Failed to Start
If you see "Container failed to start" error:

1. **Check logs:**
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME" --limit 50
   ```

2. **Verify port configuration:**
   - Ensure Dockerfile uses `--port ${PORT}`
   - Ensure main.py reads `PORT` environment variable
   - Both should match (8080)

3. **Check startup timeout:**
   - Increase timeout if database initialization takes longer
   - Database sequence resets can take time

### Common Issues

**Issue:** "Database connection failed"
- **Solution:** Check `DATABASE_URL_PROD` in environment variables
- **Solution:** Ensure Supabase connection string is correct

**Issue:** "OPENROUTER_API_KEY not set"
- **Solution:** Verify API key is in environment variables
- **Solution:** Check for typos in variable names

**Issue:** "Container image not found"
- **Solution:** Ensure Docker image was pushed successfully
- **Solution:** Check image name and tag match deployment command

## 🧪 Post-Deployment Testing

After deployment, test your service:

```bash
# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')

# Test health endpoint
curl $SERVICE_URL/

# Test API documentation
curl $SERVICE_URL/docs

# Test with a simple API call
curl -X POST $SERVICE_URL/cards/generate \
  -H "Content-Type: application/json" \
  -d '{"text":"Hola"}'
```

## 📊 Monitoring

### View Logs
```bash
# Real-time logs
gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME"

# Specific error logs
gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR" --limit 20
```

### Monitor Performance
```bash
# Check service metrics
gcloud run services describe $SERVICE_NAME --region=$REGION
```

## 🔐 Security Notes

1. **Never commit** environment files to git
2. **Use secrets management** for production credentials
3. **Enable Cloud Armor** if you need IP whitelisting
4. **Set up Cloud Monitoring** for production alerts

## 🔄 Updating the Deployment

To update your deployment:

```bash
# Make changes to code
# Build new image
docker build -t gcr.io/$PROJECT_ID/$IMAGE_NAME:latest .
docker push gcr.io/$PROJECT_ID/$IMAGE_NAME:latest

# Deploy new version
gcloud run deploy $SERVICE_NAME \
  --image=gcr.io/$PROJECT_ID/$IMAGE_NAME:latest \
  --region=$REGION \
  --platform=managed \
  --env-vars-file=gcloud_env.txt
```

---

**Need help?** Check the Google Cloud Run documentation: https://cloud.google.com/run/docs
