#!/usr/bin/env bash
# IndexNow ping script — notifies all participating search engines of URL changes
# Usage: ./scripts/indexnow-ping.sh [optional: space-separated URLs to submit]

set -euo pipefail

HOST="scottysgardeninglab.com"
KEY="d9361b83e164e7ce6ca0bc5405beab3d"
KEY_LOCATION="https://${HOST}/${KEY}.txt"

# Default URLs to submit (all pages)
if [ $# -gt 0 ]; then
  URLS=("$@")
else
  URLS=(
    "https://${HOST}/"
    "https://${HOST}/success/"
  )
fi

# Build JSON URL list
URL_JSON=$(printf '"%s",' "${URLS[@]}")
URL_JSON="[${URL_JSON%,}]"

PAYLOAD=$(cat <<EOF
{
  "host": "${HOST}",
  "key": "${KEY}",
  "keyLocation": "${KEY_LOCATION}",
  "urlList": ${URL_JSON}
}
EOF
)

# All IndexNow-participating search engines
ENGINES=(
  "https://api.indexnow.org/IndexNow"
  "https://www.bing.com/IndexNow"
  "https://yandex.com/indexnow"
  "https://searchadvisor.naver.com/indexnow"
  "https://search.seznam.cz/IndexNow"
)

echo "IndexNow: submitting ${#URLS[@]} URL(s) to ${#ENGINES[@]} search engines"
echo ""

for ENGINE in "${ENGINES[@]}"; do
  printf "  %-50s" "${ENGINE}"
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${ENGINE}" \
    -H "Content-Type: application/json; charset=utf-8" \
    -d "${PAYLOAD}" \
    --max-time 10 2>/dev/null || echo "ERR")

  if [ "${HTTP_CODE}" = "200" ] || [ "${HTTP_CODE}" = "202" ]; then
    echo "OK (${HTTP_CODE})"
  else
    echo "WARN (${HTTP_CODE})"
  fi
done

echo ""
echo "Done."
