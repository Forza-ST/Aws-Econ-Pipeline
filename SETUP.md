# AWS Economic Analysis Pipeline — Setup Guide
**Repo:** Forza-ST/Aws-Econ-Pipeline
**Local path:** `C:\Users\ForzaPC2\Documents\Projects\Job-Prep-Projects\AI-Data-Architect-Project`

---

## Before You Start — One-Time Setup

### Step 0: Tools to install on Windows
Open **PowerShell as Administrator** and run each block:

```powershell
# 1. Python 3.11
winget install Python.Python.3.11

# 2. AWS CLI v2
winget install Amazon.AWSCLI

# 3. Terraform
winget install Hashicorp.Terraform

# 4. Git (if not installed)
winget install Git.Git

# 5. Confirm versions
python --version       # 3.11.x
aws --version          # 2.x
terraform --version    # 1.7.x
git --version          # 2.x
```

### Step 1: Create the GitHub repo
1. Go to https://github.com/Forza-ST
2. Click **New repository**
3. Name it: `Aws-Econ-Pipeline`
4. Set to **Public**
5. **Do NOT** initialize with README (we'll push from local)
6. Click **Create repository**

### Step 2: Clone and set up this project
```powershell
cd "C:\Users\ForzaPC2\Documents\Projects\Job-Prep-Projects\AI-Data-Architect-Project"

# Initialize git in THIS folder (which already has all the code)
git init
git remote add origin https://github.com/Forza-ST/Aws-Econ-Pipeline.git

# CRITICAL: verify .gitignore is in place before first commit
cat .gitignore   # should show long list of ignored patterns
```

### Step 3: Configure AWS credentials (local dev only)
```powershell
aws configure
# Enter:
#   AWS Access Key ID:     [your key - ONLY for local dev, never commit]
#   AWS Secret Access Key: [your secret - ONLY for local dev, never commit]
#   Default region:        us-east-1
#   Default output format: json
```

### Step 4: Python virtual environment
```powershell
cd "C:\Users\ForzaPC2\Documents\Projects\Job-Prep-Projects\AI-Data-Architect-Project"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pre-commit install     # installs pre-commit hooks
```

### Step 5: Create your .env file
```powershell
copy .env.example .env
# Then open .env in your IDE and fill in your values
# .env is in .gitignore — it will NEVER be committed
```

---

## Phase 1: First Commit — Repo Structure Only

**Goal:** Push skeleton to GitHub, verify CI passes, no secrets leaked.

```powershell
git add .
git status  # review — make sure .env, *.tfvars, backend.hcl are NOT listed
git commit -m "feat: initial repo structure with security safeguards"
git branch -M main
git push -u origin main
```

**After pushing:**
1. Go to https://github.com/Forza-ST/Aws-Econ-Pipeline/actions
2. You should see the **CI** workflow start automatically
3. The **Secret Scan (Gitleaks)** job runs first — verify it passes
4. **Terraform Validate** will run but pass with `-backend=false` (no state bucket needed yet)

**Expected CI result:** All green ✓ (no real AWS needed yet — just linting + secret scan)

---

## Phase 2: Bootstrap AWS Infrastructure

**Goal:** Create S3 state bucket, DynamoDB lock table, and GitHub OIDC role.

> ⚠️ **Cost check:** This phase creates resources that cost nothing when idle.
> S3 state bucket: <$0.01/month. DynamoDB: free tier.

```powershell
# Run the bootstrap script
bash scripts/bootstrap_aws.sh dev

# This script outputs the IAM role ARN — copy it.
# Example: arn:aws:iam::123456789012:role/econ-pipeline-github-actions-deploy
```

**After running bootstrap:**
1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `AWS_DEPLOY_ROLE_ARN`
4. Value: (paste the ARN the script printed)
5. Click **Add secret**

**Also add these repository variables** (not secrets):
- Settings → Actions → Variables → New variable
- `ENVIRONMENT` = `dev`

---

## Phase 3: Store API Keys Securely

**Goal:** Get free API keys and store them in AWS Secrets Manager (NOT in git).

**Get your free API keys:**
| Service | URL | Time to get |
|---------|-----|-------------|
| FRED    | https://fredaccount.stlouisfed.org/apikeys | 2 minutes |
| BLS     | https://data.bls.gov/registrationEngine/ | 2 minutes |
| Metals (optional) | https://metals-api.com | 2 minutes |

> Note: yfinance (stocks, oil, gold futures) requires NO API key.
> forex collector uses open.er-api.com which also requires NO key.
> You can get full functionality with just the FRED key.

```powershell
# Store keys in Secrets Manager — you'll be prompted, keys never touch git
bash scripts/setup_secrets.sh dev
```

**Verify in AWS console:**
- Go to AWS Console → Secrets Manager → `econ-pipeline/dev/api-keys`
- You should see the secret (but not the values unless you click "Retrieve")

---

## Phase 4: Deploy Infrastructure with Terraform

**Goal:** Create S3 data lake buckets, Lambda functions, Glue jobs, Athena workgroup.

**Estimated cost for dev:** ~$1-3/month (mostly S3 storage, Glue on-demand)

```powershell
# Copy and fill in tfvars
cd infrastructure\terraform\environments\dev
copy terraform.tfvars.example terraform.tfvars
# Open terraform.tfvars in your IDE — it's git-ignored
# Fill in lambda_zip_path (leave default for now)

# Copy backend config
copy backend.hcl.example backend.hcl
# Open backend.hcl in your IDE
# Fill in the state bucket name from the bootstrap script output
```

**In your IDE, open `backend.hcl` and update:**
```hcl
bucket         = "econ-pipeline-tfstate-dev-YOUR_ACCOUNT_ID"
key            = "econ-pipeline/dev/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "econ-pipeline-tfstate-lock"
encrypt        = true
```

```powershell
terraform init -backend-config=backend.hcl
terraform plan    # review what will be created
terraform apply   # type 'yes' to confirm
```

**Verify in AWS console:**
- S3 → 3 buckets created: `econ-pipeline-raw-dev`, `econ-pipeline-clean-dev`, `econ-pipeline-curated-dev`
- Lambda → 5 functions: `econ-pipeline-dev-*-collector`
- Athena → workgroup: `econ-pipeline-dev`

---

## Phase 5: Run the Collectors Manually

**Goal:** Test each Lambda collector and verify data lands in S3.

```powershell
# Activate venv if not active
.venv\Scripts\activate

# Test locally first (reads from .env, writes to real S3)
cd src\collectors
python fred_collector.py

# Invoke via AWS CLI (invokes the deployed Lambda)
aws lambda invoke \
  --function-name econ-pipeline-dev-fred-collector \
  --payload "{}" \
  --cli-binary-format raw-in-base64-out \
  response.json
cat response.json

# Run all collectors
aws lambda invoke --function-name econ-pipeline-dev-fred-collector        --payload "{}" --cli-binary-format raw-in-base64-out /dev/null
aws lambda invoke --function-name econ-pipeline-dev-yfinance-collector    --payload "{}" --cli-binary-format raw-in-base64-out /dev/null
aws lambda invoke --function-name econ-pipeline-dev-bls-collector         --payload "{}" --cli-binary-format raw-in-base64-out /dev/null
aws lambda invoke --function-name econ-pipeline-dev-forex-collector       --payload "{}" --cli-binary-format raw-in-base64-out /dev/null
```

**Verify data in S3:**
```powershell
aws s3 ls s3://econ-pipeline-raw-dev/raw/ --recursive
# Should show JSON files for each source:
# raw/fred/2024/01/15/CPIAUCSL.json
# raw/yfinance/2024/01/15/GSPC.json
# raw/forex/2024/01/15/usd_rates.json
```

---

## Phase 6: Run the Silver Transform (Glue Job)

**Goal:** Convert raw JSON → clean Parquet in the silver zone.

```powershell
# Option A: Run locally (faster for dev, uses your AWS credentials)
cd src\transforms
python glue_silver_job.py \
  --raw_bucket econ-pipeline-raw-dev \
  --clean_bucket econ-pipeline-clean-dev

# Option B: Run as Glue Job via AWS CLI
aws glue start-job-run \
  --job-name econ-pipeline-silver-transform \
  --arguments "--raw_bucket=econ-pipeline-raw-dev,--clean_bucket=econ-pipeline-clean-dev"
```

**Verify Parquet in S3:**
```powershell
aws s3 ls s3://econ-pipeline-clean-dev/clean/ --recursive
# Should show:
# clean/fred/2024/01/CPIAUCSL.parquet
# clean/market/2024/01/GSPC.parquet
```

---

## Phase 7: Query with Athena

**Goal:** Verify data quality and run your first economic analysis query.

**In AWS Console → Athena → Query Editor:**
1. Select workgroup: `econ-pipeline-dev`
2. Create the database:
```sql
CREATE DATABASE IF NOT EXISTS econ_db;
```

3. Create external table for FRED data:
```sql
CREATE EXTERNAL TABLE econ_db.fred_indicators (
  series_id        STRING,
  observation_date DATE,
  value            DOUBLE,
  vintage_date     DATE,
  source           STRING
)
STORED AS PARQUET
LOCATION 's3://econ-pipeline-clean-dev/clean/fred/'
TBLPROPERTIES ('parquet.compress'='SNAPPY');
```

4. Run your first economic analysis:
```sql
-- CPI trend last 24 months
SELECT
  observation_date,
  value AS cpi_index,
  value - LAG(value, 12) OVER (ORDER BY observation_date) AS yoy_change
FROM econ_db.fred_indicators
WHERE series_id = 'CPIAUCSL'
ORDER BY observation_date DESC
LIMIT 24;
```

> 💡 **Interview answer for this query:** "I use Athena's window functions to compute year-over-year changes directly in the query layer — this avoids storing pre-computed deltas and gives analysts flexibility to compute any period comparison on the fly."

---

## Phase 8: Run ML Modules

**Goal:** Generate cross-asset correlation matrix and Prophet forecasts.

```powershell
# Run correlation engine locally
cd src\ml
python correlation_engine.py
# Reads from clean bucket, writes correlation_matrix.parquet to curated bucket

# Run forecasting
python forecasting.py
# Generates 90-day forecasts for CPI, Oil, Gold
```

**Verify outputs:**
```powershell
aws s3 ls s3://econ-pipeline-curated-dev/curated/ --recursive
# curated/correlation_matrix/2024/01/correlation_matrix.parquet
# curated/forecasts/2024/01/cpi_forecast.parquet
# curated/forecasts/2024/01/wti_oil_forecast.parquet
```

---

## Phase 9: Connect GitHub Actions Deploy

**Goal:** Push code changes and verify the full CI/CD pipeline runs.

```powershell
# Package Lambda functions
cd src\collectors
pip install -r requirements.txt -t package/
xcopy *.py package\ /Y
cd package
# Use PowerShell to zip (or install 7-zip)
Compress-Archive -Path . -DestinationPath ..\..\..\lambda_collectors.zip -Force
cd ..\..\..
```

```powershell
git add src/ tests/ configs/ .github/
git commit -m "feat: add collectors, transforms, ML modules, and Airflow DAG"
git push origin main
```

**Watch the GitHub Actions run:**
1. Go to https://github.com/Forza-ST/Aws-Econ-Pipeline/actions
2. You should see both **CI** and **Deploy** workflows trigger
3. CI: secret scan → lint → test → terraform validate
4. Deploy: OIDC auth → package Lambda → terraform plan → terraform apply

---

## Phase 10: Set Up Branch Protection (Security)

**Goal:** Prevent direct pushes to main, require PR reviews and CI to pass.

1. Go to GitHub repo → **Settings** → **Branches**
2. Click **Add branch protection rule**
3. Branch name pattern: `main`
4. Check:
   - ✅ Require a pull request before merging
   - ✅ Require status checks to pass before merging
   - ✅ Add status checks: `Secret Scan (Gitleaks)`, `Lint (Ruff + Black)`, `Unit Tests`
   - ✅ Require branches to be up to date before merging
   - ✅ Do not allow bypassing the above settings
5. Click **Create**

---

## Cost Summary for Demo

| Service | Dev Usage | Estimated Monthly Cost |
|---------|-----------|----------------------|
| S3 storage | ~500MB Parquet | ~$0.01 |
| S3 requests | ~10k/month | ~$0.01 |
| Lambda | 5 functions × daily runs | Free tier ($0) |
| Glue Python Shell | 1 DPH × daily | ~$2.00 |
| Athena | ~10 queries × 1MB avg | ~$0.00 |
| Secrets Manager | 1 secret | ~$0.40 |
| EventBridge | DISABLED by default | $0.00 |
| **Total** | | **~$2.50/month** |

**To minimize further:** Disable EventBridge rules (already done in Terraform) and run collectors manually. Glue only charges when a job runs.

---

## Security Safeguards Checklist

Before each push, verify:

- [ ] `git status` shows NO `.env`, `backend.hcl`, `terraform.tfvars`, `*.pem`, `*.key`
- [ ] `git log --all --full-history -- "*.pem"` returns nothing
- [ ] Gitleaks pre-commit hook is installed: `pre-commit run --all-files`
- [ ] No hardcoded account IDs, ARNs, or keys in Python files
- [ ] Lambda environment variables contain NO secrets (only Secrets Manager ARN)
- [ ] S3 buckets have `public_access_block = true` (enforced by Terraform)
- [ ] Athena workgroup has `bytes_scanned_cutoff_per_query` set (cost guard)
- [ ] IAM roles follow least-privilege (Lambda can only write to `/raw/*` prefix)
- [ ] GitHub Actions uses OIDC (no `AWS_ACCESS_KEY_ID` in GitHub Secrets)

---

## Key Interview Talking Points

**On security:**
> "I used OIDC federated credentials for GitHub Actions — no long-lived AWS keys are stored anywhere in GitHub. The IAM role uses a condition that scopes access to only the specific repository and org, so even if someone forks the repo, they can't assume the role."

**On cost:**
> "For a demo pipeline, I chose architecture that costs ~$2.50/month instead of $300/month. Redshift replaced with Athena + Parquet (pay-per-query), MWAA replaced with scheduled Lambda, SageMaker replaced with Prophet in Lambda. The schema and data model are identical — swapping to production-scale services is a config change, not an architecture change."

**On data quality:**
> "Every series has an expectation suite — CPI must be between 0 and 500, unemployment between 1 and 30%, no future dates, no duplicate observations. Quality runs as a Lambda gate in the Airflow DAG: if it fails, the pipeline halts before bad data reaches the warehouse."

**On secrets:**
> "API keys are stored in Secrets Manager and fetched at Lambda runtime via the IAM execution role — they never appear in environment variables, logs, or git history. The .gitignore, gitleaks pre-commit hook, and the CI gitleaks scan give us three layers of protection against accidental key exposure."

**On schema evolution:**
> "I treat the raw zone as immutable — whatever the API returns is stored exactly as-is. This means if a BLS API adds a new field, I don't lose it and I can replay the raw files through an updated transform. It's the data engineering equivalent of event sourcing."

