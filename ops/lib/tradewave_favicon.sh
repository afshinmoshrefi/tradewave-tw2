#!/usr/bin/env bash

# One favicon mapping for every TradeWave publishing surface.
# Browser-facing pages always link /favicon.png; this helper chooses the source
# asset that is copied to that URL for the current environment.

tw_favicon_source() {
  if [ "$#" -ne 2 ]; then
    echo "ERROR: tw_favicon_source requires <environment> <static-dir>" >&2
    return 2
  fi

  local environment="$1"
  local static_dir="$2"
  local filename

  case "$environment" in
    dev)     filename="favicon-white.png" ;;
    staging) filename="favicon-black.png" ;;
    prod)    filename="favicon-colour.png" ;;
    *)
      echo "ERROR: unsupported TW2_ENV for favicon: ${environment:-<unset>}" >&2
      return 2
      ;;
  esac

  local source="$static_dir/$filename"
  [ -r "$source" ] || {
    echo "ERROR: favicon source missing or unreadable: $source" >&2
    return 2
  }
  printf '%s\n' "$source"
}

tw_publish_environment_favicon() {
  if [ "$#" -ne 3 ]; then
    echo "ERROR: tw_publish_environment_favicon requires <environment> <static-dir> <destination>" >&2
    return 2
  fi

  local environment="$1"
  local static_dir="$2"
  local destination="$3"
  local source
  source="$(tw_favicon_source "$environment" "$static_dir")" || return $?

  install -m 0644 "$source" "$destination" || return $?
  echo "  OK    favicon - $(basename "$source") -> $destination (TW2_ENV=$environment)"
}
