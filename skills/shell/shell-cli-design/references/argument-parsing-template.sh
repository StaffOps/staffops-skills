#!/usr/bin/env bash
# Argument Parsing Template — getopts (POSIX) + long options

set -euo pipefail

# ═══ OPTION 1: Manual parsing (supports long options) ══════════
ACTION=""
TARGET=""
FORCE=false
OUTPUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -f|--force)   FORCE=true; shift ;;
    -o|--output)  OUTPUT="$2"; shift 2 ;;
    -h|--help)    usage; exit 0 ;;
    --)           shift; break ;;     # end of options
    -*)           echo "Unknown: $1" >&2; exit 1 ;;
    *)
      # Positional: first is action, second is target
      if [[ -z "$ACTION" ]]; then ACTION="$1"
      elif [[ -z "$TARGET" ]]; then TARGET="$1"
      else echo "Too many arguments" >&2; exit 1
      fi
      shift ;;
  esac
done

# ═══ OPTION 2: getopts (POSIX, short options only) ═════════════
# Simpler but no long options
VERBOSE=0
FILE=""

OPTIND=1
while getopts "vf:h" opt; do
  case "$opt" in
    v) VERBOSE=1 ;;
    f) FILE="$OPTARG" ;;
    h) usage; exit 0 ;;
    ?) exit 1 ;;
  esac
done
shift $((OPTIND - 1))  # remaining args in "$@"

# ═══ SUBCOMMAND PATTERN ═══════════════════════════════════════
# mytool deploy <service> --env prd
# mytool status <service>
# mytool logs <service> --tail 100

main() {
  local cmd="${1:-help}"
  shift || true

  case "$cmd" in
    deploy)  cmd_deploy "$@" ;;
    status)  cmd_status "$@" ;;
    logs)    cmd_logs "$@" ;;
    help|-h|--help) usage ;;
    *)       echo "Unknown command: $cmd" >&2; usage; exit 1 ;;
  esac
}

cmd_deploy() {
  local service="${1:?Missing service name}"
  local env="dev"
  shift
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --env) env="$2"; shift 2 ;;
      *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
  done
  echo "Deploying $service to $env"
}

cmd_status() {
  local service="${1:?Missing service name}"
  echo "Status of $service"
}

cmd_logs() {
  local service="${1:?Missing service name}"
  local tail=50
  shift
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --tail) tail="$2"; shift 2 ;;
      *) break ;;
    esac
  done
  echo "Last $tail lines for $service"
}

usage() {
  cat <<'EOF'
Usage: mytool <command> [options]

Commands:
  deploy <service> --env <env>   Deploy a service
  status <service>               Show service status
  logs <service> [--tail N]      Show service logs

Options:
  -h, --help    Show help
EOF
}

main "$@"
