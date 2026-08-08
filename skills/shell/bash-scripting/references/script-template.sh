#!/usr/bin/env bash
# Script Template — copy this as starting point for any script
set -euo pipefail

# ═══ CONSTANTS ══════════════════════════════════════════════════
readonly SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly VERSION="1.0.0"

# ═══ COLORS (only if stdout is terminal) ═══════════════════════
if [[ -t 1 ]]; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; NC=''
fi

# ═══ LOGGING ════════════════════════════════════════════════════
log()  { echo -e "${GREEN}[INFO]${NC} $*" >&2; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*" >&2; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()  { err "$@"; exit 1; }

# ═══ CLEANUP TRAP ═══════════════════════════════════════════════
cleanup() {
  local exit_code=$?
  # Remove temp files, restore state, etc.
  [[ -n "${TMPDIR:-}" ]] && rm -rf "$TMPDIR"
  exit $exit_code
}
trap cleanup EXIT

# ═══ USAGE ══════════════════════════════════════════════════════
usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [OPTIONS] <argument>

Description of what this script does.

Options:
  -e, --env ENV     Target environment (dev|hml|prd) [required]
  -d, --dry-run     Show what would be done without doing it
  -v, --verbose     Enable verbose output
  -h, --help        Show this help
  --version         Show version

Examples:
  ${SCRIPT_NAME} -e dev myservice
  ${SCRIPT_NAME} --dry-run -e prd deploy
EOF
}

# ═══ ARGUMENT PARSING ═══════════════════════════════════════════
ENV=""
DRY_RUN=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--env)     ENV="$2"; shift 2 ;;
    -d|--dry-run) DRY_RUN=true; shift ;;
    -v|--verbose) VERBOSE=true; shift ;;
    -h|--help)    usage; exit 0 ;;
    --version)    echo "$VERSION"; exit 0 ;;
    --)           shift; break ;;
    -*)           die "Unknown option: $1. Use --help for usage." ;;
    *)            break ;;
  esac
done

# Remaining positional args
ARGUMENT="${1:-}"

# ═══ VALIDATION ═════════════════════════════════════════════════
[[ -z "$ENV" ]] && die "Missing required --env. Use --help."
[[ "$ENV" =~ ^(dev|hml|prd)$ ]] || die "Invalid env: $ENV (must be dev|hml|prd)"
[[ -z "$ARGUMENT" ]] && die "Missing required argument. Use --help."

# Check dependencies
command -v jq >/dev/null || die "jq is required but not installed"
command -v curl >/dev/null || die "curl is required but not installed"

# ═══ MAIN LOGIC ═════════════════════════════════════════════════
main() {
  log "Starting ${SCRIPT_NAME} v${VERSION}"
  log "Environment: ${ENV}, Argument: ${ARGUMENT}"

  TMPDIR="$(mktemp -d)"

  if [[ "$DRY_RUN" == true ]]; then
    log "[DRY-RUN] Would process: $ARGUMENT"
    return 0
  fi

  # Your logic here
  log "Processing $ARGUMENT..."

  log "Done."
}

main "$@"
