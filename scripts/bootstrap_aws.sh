#!/usr/bin/env bash
# ── One-time AWS bootstrap — run ONCE before first Terraform apply ────────
# Creates: S3 state bucket, DynamoDB lock table, OIDC provider for GitHub Actions
# Prerequisites: AWS CLI configured with admin permissions

set -euo pipefail

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"
PROJECT="econ-pipeline"
ENVIRONMENT="${1:-dev}"
GITHUB_ORG="Forza-ST"
REPO_NAME="Aws-Econ-Pipeline"

echo "Bootstrapping AWS for: $PROJECT/$ENVIRONMENT in $ACCOUNT_ID/$REGION"

# ── 1. Terraform state bucket ─────────────────────────────────────────────
STATE_BUCKET="${PROJECT}-tfstate-${ENVIRONMENT}-${ACCOUNT_ID}"
echo "Creating state bucket: $STATE_BUCKET"
aws s3 mb "s3://$STATE_BUCKET" --region "$REGION" 2>/dev/null || echo "  (already exists)"
aws s3api put-bucket-versioning \
  --bucket "$STATE_BUCKET" \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption \
  --bucket "$STATE_BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block \
  --bucket "$STATE_BUCKET" \
  --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# ── 2. DynamoDB state lock table ──────────────────────────────────────────
LOCK_TABLE="${PROJECT}-tfstate-lock"
echo "Creating DynamoDB lock table: $LOCK_TABLE"
aws dynamodb create-table \
  --table-name "$LOCK_TABLE" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION" 2>/dev/null || echo "  (already exists)"

# ── 3. GitHub Actions OIDC provider (no long-lived keys in GitHub!) ────────
echo "Setting up GitHub OIDC provider..."
aws iam create-open-id-connect-provider \
  --url "https://token.actions.githubusercontent.com" \
  --client-id-list "sts.amazonaws.com" \
  --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" \
  2>/dev/null || echo "  (OIDC provider already exists)"

# ── 4. GitHub Actions deploy IAM role ─────────────────────────────────────
ROLE_NAME="${PROJECT}-github-actions-deploy"
echo "Creating IAM role: $ROLE_NAME"
TRUST_POLICY=$(cat <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
      },
      "StringLike": {
        "token.actions.githubusercontent.com:sub": "repo:${GITHUB_ORG}/${REPO_NAME}:*"
      }
    }
  }]
}
POLICY
)

aws iam create-role \
  --role-name "$ROLE_NAME" \
  --assume-role-policy-document "$TRUST_POLICY" \
  --description "GitHub Actions deploy role for $PROJECT — OIDC federated, no long-lived keys" \
  2>/dev/null || echo "  (role already exists)"

# Attach minimum needed policies (scope down in production)
aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/AmazonS3FullAccess" 2>/dev/null || true
aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/AWSLambda_FullAccess" 2>/dev/null || true
aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/AWSGlueConsoleFullAccess" 2>/dev/null || true
aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/IAMFullAccess" 2>/dev/null || true
aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/SecretsManagerReadWrite" 2>/dev/null || true
aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess" 2>/dev/null || true
aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/AmazonAthenaFullAccess" 2>/dev/null || true

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

# ── 5. Create backend.hcl from template ───────────────────────────────────
cat > "infrastructure/terraform/environments/${ENVIRONMENT}/backend.hcl" <<BACKEND
bucket         = "${STATE_BUCKET}"
key            = "${PROJECT}/${ENVIRONMENT}/terraform.tfstate"
region         = "${REGION}"
dynamodb_table = "${LOCK_TABLE}"
encrypt        = true
BACKEND
echo "  backend.hcl written (git-ignored)"

echo ""
echo "══════════════════════════════════════════════════════════"
echo "✓ Bootstrap complete!"
echo ""
echo "Next steps:"
echo "  1. Add this secret to GitHub repo:"
echo "     AWS_DEPLOY_ROLE_ARN = ${ROLE_ARN}"
echo ""
echo "  2. Add these GitHub repo variables (not secrets):"
echo "     ENVIRONMENT = ${ENVIRONMENT}"
echo ""
echo "  3. Run Terraform:"
echo "     cd infrastructure/terraform/environments/${ENVIRONMENT}"
echo "     terraform init -backend-config=backend.hcl"
echo "     terraform plan -var-file=terraform.tfvars"
echo "══════════════════════════════════════════════════════════"
