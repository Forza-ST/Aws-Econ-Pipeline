#!/usr/bin/env bash
# Attach Terraform deploy policies to the GitHub OIDC role (run once after bootstrap).
set -euo pipefail

PROJECT="${PROJECT:-econ-pipeline}"
ROLE_NAME="${PROJECT}-github-actions-deploy"

POLICIES=(
  "arn:aws:iam::aws:policy/IAMFullAccess"
  "arn:aws:iam::aws:policy/SecretsManagerReadWrite"
  "arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess"
  "arn:aws:iam::aws:policy/AmazonAthenaFullAccess"
)

for arn in "${POLICIES[@]}"; do
  echo "Attaching $arn to $ROLE_NAME"
  aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn "$arn"
done

echo "Done. Re-run the Deploy workflow on GitHub Actions."
