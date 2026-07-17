#!/usr/bin/env bash
# PreToolUse/Bash: auto-allow curl commands that can only reach localhost.
# Anything else prints nothing and falls through to the normal permission flow.
#
# An "allow" here approves the whole command line, not just the curl part, so a
# lone curl call is the only shape accepted: no chaining, no substitution, and
# no flags that point the request somewhere other than the URL that's written.
set -uo pipefail

cmd=$(jq -r '.tool_input.command // empty')

[[ $cmd =~ ^(time[[:space:]]+)?curl[[:space:]] ]] || exit 0
[[ $cmd =~ [\;\&\|\<\>\`] || $cmd == *'$('* ]] && exit 0
[[ $cmd =~ (^|[[:space:]])(-x|--proxy|--resolve|--connect-to|-K|--config)([[:space:]]|=) ]] && exit 0

urls=$(grep -oE 'https?://[^[:space:]"'"'"']+' <<<"$cmd") || exit 0
[[ -n $urls ]] || exit 0

while read -r u; do
  authority=${u#*://}
  authority=${authority%%[/?#]*}
  authority=${authority##*@}
  if [[ $authority == \[* ]]; then
    host=${authority%%]*}]
  else
    host=${authority%%:*}
  fi
  case $host in
    localhost | 127.0.0.1 | '[::1]') ;;
    *) exit 0 ;;
  esac
done <<<"$urls"

jq -n '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",permissionDecisionReason:"curl targets localhost only"}}'
