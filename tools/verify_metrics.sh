#!/usr/bin/env bash
set -euo pipefail

# verify_metrics.sh — PR gate: extract and verify Prometheus metric names from SKILL.md files
# Usage: verify_metrics.sh --all | --skill <name>

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_ROOT="${SCRIPT_DIR}/../skills"

# Metrics from components known to not be scraped (by design — no ServiceMonitor/PodMonitor)
NOT_SCRAPED_ALLOWLIST=(
  "nginx_ingress_controller_"
  "velero_"
  "certmanager_acme_"
  "sonarqube_"
  "datahub_"
  "superset_"
  "backstage_"
  "keycloak_failed_login"
  "keycloak_logins_"
  "keycloak_request_"
  "kubescape_controls_"
  "kubescape_vulnerabilities_"
  "defectdojo_"
)

# --- Argument parsing ---
MODE=""
SKILL_FILTER=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) MODE="all"; shift ;;
    --skill) MODE="skill"; SKILL_FILTER="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 --all | --skill <name>"; exit 0 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done
[[ -z "$MODE" ]] && { echo "ERROR: specify --all or --skill <name>"; exit 1; }

# --- Find SKILL.md files ---
if [[ "$MODE" == "skill" ]]; then
  mapfile -t SKILL_FILES < <(find "$SKILLS_ROOT" -path "*/${SKILL_FILTER}/SKILL.md" -type f)
  [[ ${#SKILL_FILES[@]} -eq 0 ]] && { echo "ERROR: skill '$SKILL_FILTER' not found"; exit 1; }
else
  mapfile -t SKILL_FILES < <(find "$SKILLS_ROOT" -name "SKILL.md" -type f | sort)
fi

# --- Extract metrics from files ---
declare -A METRICS_MAP  # metric -> skill_file (first occurrence)
for f in "${SKILL_FILES[@]}"; do
  skill_name="$(basename "$(dirname "$f")")"
  # Extract metric-like names: word_word pattern (min 2 segments with underscore)
  # Filter out markdown/code noise: require at least one known prefix or >=2 underscores
  while IFS= read -r metric; do
    [[ -z "$metric" ]] && continue
    # Skip common false positives
    [[ "$metric" =~ ^(set_euo|usr_bin|usr_local|tmp_|bin_|src_|app_|var_|etc_) ]] && continue
    [[ "$metric" =~ ^(docker_run|docker_build|helm_|kubectl_|git_|pip_|apt_) ]] && continue
    [[ ${#metric} -lt 6 ]] && continue
    # Only keep if not already seen (first file wins)
    if [[ -z "${METRICS_MAP[$metric]+x}" ]]; then
      METRICS_MAP["$metric"]="$skill_name"
    fi
  done < <(grep -oP '(?<![`/\w.-])[a-z][a-z0-9]*(?:_[a-z][a-z0-9]*){2,}(?![`/\w.-])' "$f" \
    | grep -vE '^(service_name|deployment_environment|cloud_provider|http_status|error_type)$' \
    | sort -u)
done

TOTAL=${#METRICS_MAP[@]}
[[ $TOTAL -eq 0 ]] && { echo "No metrics extracted."; exit 0; }

# --- Verify against VictoriaMetrics ---
declare -A METRIC_STATUS
CONFIRMED=0; INEXISTENT=0; NOT_SCRAPED=0; UNVERIFIED=0

check_allowlist() {
  local m="$1"
  for prefix in "${NOT_SCRAPED_ALLOWLIST[@]}"; do
    [[ "$m" == ${prefix}* ]] && return 0
  done
  return 1
}

verify_metric() {
  local metric="$1"
  local endpoint="${VM_READ_ENDPOINT}/api/v1/series"
  local resp
  resp=$(curl -sf --max-time 5 -G "$endpoint" \
    --data-urlencode "match[]=${metric}" \
    --data-urlencode "start=$(date -d '-24 hours' -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -v-24H -u +%Y-%m-%dT%H:%M:%SZ)" \
    --data-urlencode "end=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --data-urlencode "limit=1" 2>/dev/null) || return 2
  local count
  count=$(echo "$resp" | grep -c '"__name__"' 2>/dev/null || echo "0")
  [[ "$count" -gt 0 ]] && return 0 || return 1
}

for metric in "${!METRICS_MAP[@]}"; do
  if check_allowlist "$metric"; then
    METRIC_STATUS["$metric"]="NOT-SCRAPED-BY-DESIGN"
    NOT_SCRAPED=$((NOT_SCRAPED + 1))
  elif [[ -n "${VM_READ_ENDPOINT:-}" ]]; then
    if verify_metric "$metric"; then
      METRIC_STATUS["$metric"]="CONFIRMED"
      CONFIRMED=$((CONFIRMED + 1))
    else
      METRIC_STATUS["$metric"]="INEXISTENT"
      INEXISTENT=$((INEXISTENT + 1))
    fi
  else
    METRIC_STATUS["$metric"]="UNVERIFIED"
    UNVERIFIED=$((UNVERIFIED + 1))
  fi
done

# --- Output TSV ---
echo -e "metric_name\tskill_file\tstatus"
for metric in $(echo "${!METRICS_MAP[@]}" | tr ' ' '\n' | sort); do
  echo -e "${metric}\t${METRICS_MAP[$metric]}\t${METRIC_STATUS[$metric]}"
done

# --- Summary ---
echo ""
echo "=== SUMMARY ==="
echo "Total metrics extracted: $TOTAL"
echo "  CONFIRMED:              $CONFIRMED"
echo "  NOT-SCRAPED-BY-DESIGN:  $NOT_SCRAPED"
echo "  UNVERIFIED:             $UNVERIFIED"
echo "  INEXISTENT:             $INEXISTENT"

# --- Group by prefix ---
echo ""
echo "=== BY PREFIX ==="
for metric in $(echo "${!METRICS_MAP[@]}" | tr ' ' '\n' | sort); do
  echo "${metric%%_*}_"
done | sort | uniq -c | sort -rn | head -20

# --- Exit code ---
if [[ $INEXISTENT -gt 0 ]]; then
  echo ""
  echo "FAIL: $INEXISTENT metrics not found in VictoriaMetrics"
  exit 1
fi
exit 0
