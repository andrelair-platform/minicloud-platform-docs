#!/usr/bin/env bash
# Vendor brand logos for components with no built-in `diagrams` icon.
# Sources (both stable, full-colour PNG): GitHub org avatars (github.com/<org>.png)
# and the CNCF artwork repo. Best-effort + idempotent: a failed/!PNG download is skipped
# (the diagram still renders that node with its semantic fallback). Provenance table below.
#
# Usage:  bash fetch-icons.sh          (skips files already present)
#         bash fetch-icons.sh --force  (re-download everything)
set -u
cd "$(dirname "$0")/src/icons"

FORCE="${1:-}"

# filename<TAB>url  — filename MUST match the icon="..." used in the diagram modules.
CNCF="https://raw.githubusercontent.com/cncf/artwork/main/projects"
GH="https://github.com"
MAP=$(cat <<EOF
groq.png	$GH/groq.png?size=256
cloudflared.png	$GH/cloudflare.png?size=256
tailscale.png	$GH/tailscale.png?size=256
metallb.png	$GH/metallb.png?size=256
authentik.png	$GH/goauthentik.png?size=256
argo-rollouts.png	$CNCF/argo/icon/color/argo-icon-color.png
kargo.png	$GH/akuity.png?size=256
keda.png	$GH/kedacore.png?size=256
reloader.png	$GH/stakater.png?size=256
backstage.png	$CNCF/backstage/icon/color/backstage-icon-color.png
ghcr.png	$GH/github.png?size=256
openwebui.png	$GH/open-webui.png?size=256
flowise.png	$GH/FlowiseAI.png?size=256
qdrant.png	$GH/qdrant.png?size=256
langgraph.png	$GH/langchain-ai.png?size=256
crewai.png	$GH/crewAIInc.png?size=256
vllm.png	$GH/vllm-project.png?size=256
ollama.png	$GH/ollama.png?size=256
langfuse.png	$GH/langfuse.png?size=256
erpnext.png	$GH/frappe.png?size=256
matrix.png	$GH/matrix-org.png?size=256
jitsi.png	$GH/jitsi.png?size=256
plane.png	$GH/makeplane.png?size=256
longhorn.png	$CNCF/longhorn/icon/color/longhorn-icon-color.png
minio.png	$GH/minio.png?size=256
otel.png	$CNCF/opentelemetry/icon/color/opentelemetry-icon-color.png
nats.png	$CNCF/nats/icon/color/nats-icon-color.png
cilium.png	$GH/cilium.png?size=256
temporal.png	$GH/temporalio.png?size=256
docuseal.png	$GH/docusealco.png?size=256
polaris.png	$GH/FairwindsOps.png?size=256
velero.png	$GH/vmware-tanzu.png?size=256
paperless.png	$GH/paperless-ngx.png?size=256
stripe.png	$GH/stripe.png?size=256
spring.png	$GH/spring-projects.png?size=256
nextjs.png	$GH/vercel.png?size=256
express.png	$GH/expressjs.png?size=256
bullmq.png	$GH/taskforcesh.png?size=256
EOF
)

ok=0; skip=0; fail=0
while IFS=$'\t' read -r name url; do
  [ -z "$name" ] && continue
  if [ -z "$FORCE" ] && [ -f "$name" ]; then echo "skip (exists) $name"; skip=$((skip+1)); continue; fi
  tmp="$(mktemp)"
  code=$(/usr/bin/curl -sL -o "$tmp" -w '%{http_code}' --max-time 20 "$url")
  if [ "$code" = "200" ] && file -b "$tmp" | grep -qi 'PNG image'; then
    mv "$tmp" "$name"; echo "ok   $name  ($(wc -c <"$name" | tr -d ' ')b)"; ok=$((ok+1))
  else
    rm -f "$tmp"; echo "FAIL $name  [http $code] $url"; fail=$((fail+1))
  fi
done <<< "$MAP"

echo "----"
echo "downloaded=$ok  skipped=$skip  failed=$fail"
echo "Missing/failed icons keep their built-in semantic fallback — the diagram still renders."
