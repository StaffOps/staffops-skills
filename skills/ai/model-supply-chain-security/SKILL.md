---
name: model-supply-chain-security
description: "Use when securing the model artifact supply chain — verifying model provenance, detecting tampered weights, signing model artifacts, scanning for embedded malware in model files, and ensuring fine-tuned models haven't been poisoned."
---
# Model Supply Chain Security

## When to use

- Downloading open-weight models from HuggingFace/model hubs
- Deploying self-hosted models where artifact integrity matters
- Implementing model signing for internal model registry
- Scanning model files for embedded code/malware (pickle exploits)
- Verifying that fine-tuned models haven't been tampered with
- Building provenance chains for compliance (EU AI Act supply chain requirements)

## When NOT to use

- Securing API-based model usage (provider handles this; use `ai-security-hardening`)
- Model governance/lifecycle (use `model-registry-governance`)
- Defending against data poisoning during training (use `ai-security-hardening`)
- Agent permission scoping (use `ai-agent-security`)

## Steps

1. **Verify model provenance on download**:
   ```bash
   # NEVER download models without verifying checksums
   # HuggingFace — verify SHA256 of each file
   pip install huggingface_hub

   python -c "
   from huggingface_hub import hf_hub_download, model_info
   info = model_info('meta-llama/Meta-Llama-3.1-8B-Instruct')
   print(f'Model: {info.modelId}')
   print(f'SHA: {info.sha}')
   print(f'Last modified: {info.lastModified}')
   print(f'Siblings: {len(info.siblings)} files')
   # Verify each file hash matches
   for sibling in info.siblings:
       print(f'  {sibling.rfilename}: {sibling.lfs.sha256 if sibling.lfs else \"no-lfs\"}')
   "
   ```

2. **Scan model files for embedded code** (pickle attacks):
   ```bash
   # Install model scanner
   pip install modelscan

   # Scan before loading ANY model file
   modelscan --path ./downloaded-model/
   # Output: lists any embedded code, imports, or suspicious patterns

   # Alternative: fickling for pickle-specific analysis
   pip install fickling
   fickling --check model.pkl
   ```

   ```python
   # Automated scan in download pipeline
   import subprocess
   from pathlib import Path

   def scan_model_artifacts(model_dir: str) -> dict:
       """Scan all model files for embedded code/malware."""
       result = subprocess.run(
           ["modelscan", "--path", model_dir, "--output", "json"],
           capture_output=True, text=True
       )
       scan = json.loads(result.stdout)

       if scan.get("issues"):
           raise SecurityError(
               f"Model scan found {len(scan['issues'])} issues: "
               f"{[i['description'] for i in scan['issues']]}"
           )
       return {"status": "clean", "files_scanned": scan["summary"]["scanned"]}
   ```

3. **Sign model artifacts** (cosign for model files):
   ```bash
   # Sign model after internal validation
   # Create tarball of model directory
   tar -czf model-llama3-8b-v1.tar.gz ./Meta-Llama-3.1-8B-Instruct/

   # Generate SHA256 manifest
   find ./Meta-Llama-3.1-8B-Instruct/ -type f -exec sha256sum {} \; > model-manifest.sha256

   # Sign the manifest with cosign
   cosign sign-blob --key cosign.key model-manifest.sha256 \
     --output-signature model-manifest.sha256.sig \
     --output-certificate model-manifest.sha256.cert

   # Verify before deployment
   cosign verify-blob --key cosign.pub model-manifest.sha256 \
     --signature model-manifest.sha256.sig
   ```

4. **Secure model storage and access**:
   ```yaml
   # Model artifacts stored in S3 with versioning + access controls
   # terraform/model-storage.tf
   resource "aws_s3_bucket" "model_artifacts" {
     bucket = "org-model-artifacts-${var.environment}"

     versioning {
       enabled = true  # Never lose a model version
     }

     server_side_encryption_configuration {
       rule {
         apply_server_side_encryption_by_default {
           sse_algorithm = "aws:kms"
           kms_master_key_id = aws_kms_key.model_encryption.arn
         }
       }
     }

     tags = {
       Environment = var.environment
       CostCenter  = "Platform-Infrastructure"
       Purpose     = "ML Model Artifacts"
     }
   }

   resource "aws_s3_bucket_policy" "model_access" {
     bucket = aws_s3_bucket.model_artifacts.id
     policy = jsonencode({
       Version = "2012-10-17"
       Statement = [{
         Effect = "Allow"
         Principal = { AWS = var.inference_role_arn }
         Action = ["s3:GetObject"]
         Resource = "${aws_s3_bucket.model_artifacts.arn}/*"
         Condition = {
           StringEquals = { "s3:ExistingObjectTag/signed": "true" }
         }
       }]
     })
   }
   ```

5. **Fine-tuning integrity validation**:
   ```python
   # Validate fine-tuned model hasn't been poisoned
   def validate_fine_tuned_model(
       base_model_path: str,
       fine_tuned_path: str,
       eval_dataset_path: str,
       max_degradation: float = 0.05  # 5% quality drop = suspicious
   ) -> dict:
       """Compare fine-tuned model against base on safety benchmarks."""
       base_scores = run_safety_eval(base_model_path, eval_dataset_path)
       ft_scores = run_safety_eval(fine_tuned_path, eval_dataset_path)

       checks = {
           "refusal_rate": {
               "base": base_scores["refusal_rate"],
               "fine_tuned": ft_scores["refusal_rate"],
               "degraded": ft_scores["refusal_rate"] < base_scores["refusal_rate"] - max_degradation,
           },
           "safety_score": {
               "base": base_scores["safety_score"],
               "fine_tuned": ft_scores["safety_score"],
               "degraded": ft_scores["safety_score"] < base_scores["safety_score"] - max_degradation,
           }
       }

       if any(c["degraded"] for c in checks.values()):
           raise SecurityError(f"Fine-tuned model failed safety validation: {checks}")

       return {"status": "passed", "checks": checks}
   ```

6. **Model SBOM (Software Bill of Materials)**:
   ```yaml
   # model-sbom.yaml — track what went into the model
   model_id: llama3-8b-finetuned-ops-v1
   base_model:
     source: meta-llama/Meta-Llama-3.1-8B-Instruct
     version: "2024-07-23"
     sha256: "abc123..."
     license: llama3.1
   fine_tuning:
     dataset: "internal-ops-conversations-v2"
     dataset_hash: "def456..."
     method: LoRA
     epochs: 3
     date: "2025-07-01"
     trainer: platform-team
   dependencies:
     - transformers==4.42.0
     - torch==2.3.0
     - peft==0.11.0
   validation:
     safety_eval_passed: true
     quality_eval_score: 0.89
     modelscan_clean: true
   signatures:
     manifest_sig: "model-manifest.sha256.sig"
     signed_by: "platform-team cosign key"
     signed_date: "2025-07-02"
   ```

## Decision tree

```
IF downloading model from public hub (HuggingFace, etc.):
  → Verify checksums (step 1)
  → Scan for embedded code (step 2)
  → NEVER load .pkl files without scanning
IF deploying self-hosted model to production:
  → Sign artifact (step 3)
  → Only allow signed models in prod (S3 policy, step 4)
  → Create SBOM (step 6)
IF using a fine-tuned model:
  → Validate against base model safety benchmarks (step 5)
  → Document training data provenance in SBOM
  → Sign after validation
IF compliance audit (EU AI Act):
  → Produce SBOM for all deployed models
  → Show provenance chain (base → fine-tune → validation → signing → deploy)
  → Demonstrate tamper detection capability
IF model format is pickle-based (.pkl, .pt):
  → HIGH RISK — scan is mandatory, no exceptions
  → Prefer safetensors format (no arbitrary code execution)
```

## Anti-patterns

- ❌ Loading HuggingFace models without verifying checksums
- ❌ Using pickle-format models without scanning (`torch.load` executes arbitrary code)
- ❌ No signing of internal model artifacts (can't detect tampering)
- ❌ Fine-tuned models deployed without safety regression testing
- ❌ Model weights stored in git (too large, no access control)
- ❌ Same S3 bucket for model artifacts and general data (no access isolation)
- ❌ No SBOM — can't answer "what's in this model?" during an incident

## Related skills

- `model-registry-governance` — lifecycle management (this skill covers integrity)
- `ai-security-hardening` — infrastructure securing model serving
- `cosign-image-signing` — same signing patterns applied to model artifacts
- `sbom-vulnerability-management` — SBOM patterns (code deps, adapted here for models)
