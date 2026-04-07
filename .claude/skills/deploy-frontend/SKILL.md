---
name: deploy-frontend
description: Build frontend and deploy to S3 + CloudFront. Run manually from local machine when you want to deploy without waiting for CI. Requires AWS credentials and CF_DISTRIBUTION_ID env var.
disable-model-invocation: true
---

Deploy the frontend from your local machine to S3 + CloudFront.

**Prerequisites**: AWS CLI configured with credentials that have `s3:PutObject` and `cloudfront:CreateInvalidation` permissions.

## Step 1 — Build

```bash
cd frontend
VITE_API_BASE_URL="" npm run build
```

Verify `dist/` was created successfully.

## Step 2 — Sync to S3

```bash
# Sync immutable assets (JS/CSS with content hashes) — long cache
aws s3 sync dist/ s3://chatbotdeploytestv1/ \
  --exclude "index.html" \
  --cache-control "public,max-age=31536000,immutable" \
  --region ap-southeast-2

# Sync index.html — no-cache so browsers always fetch the latest
aws s3 cp dist/index.html s3://chatbotdeploytestv1/index.html \
  --cache-control "no-cache,no-store,must-revalidate" \
  --region ap-southeast-2
```

## Step 3 — CloudFront invalidation

```bash
# CF_DISTRIBUTION_ID must be set in your environment, or replace inline
aws cloudfront create-invalidation \
  --distribution-id "${CF_DISTRIBUTION_ID}" \
  --paths "/*" \
  --region ap-southeast-2
```

If `CF_DISTRIBUTION_ID` is not set, tell the user to set it: `export CF_DISTRIBUTION_ID=<your-distribution-id>`.
The CloudFront URL is https://d3qrt08bgfyl3d.cloudfront.net — find the distribution ID in the AWS Console or with:
```bash
aws cloudfront list-distributions --query "DistributionList.Items[?DomainName=='d3qrt08bgfyl3d.cloudfront.net'].Id" --output text
```

## Final report

```
✓ Frontend deployed
  Build: dist/ created
  S3: synced to s3://chatbotdeploytestv1/
  CloudFront: invalidation <id> created — changes live in ~30s
```
