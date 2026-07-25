---
id: kubectl-oidc-access
title: kubectl OIDC Access — Setup & Troubleshooting
sidebar_label: "🔑 kubectl OIDC Access"
---

# kubectl OIDC Access — Setup & Troubleshooting

The `minicloud-oidc` kubectl context authenticates via Authentik using the OIDC Authorization Code flow + PKCE (kubelogin). Getting this working end-to-end required fixing four independent bugs across four different layers. This page documents the correct configuration and the full debugging chain so it can be reproduced on any new machine.

---

## Architecture

```
Mac (kubectl)
  └─ kubelogin (oidc-login plugin)
       └─ browser → Authentik auth flow (auth.10.0.0.200.nip.io)
            └─ RS256 JWT returned to localhost:8000 callback
                 └─ kubectl presents token to k3s API (10.0.0.2:6443)
                      └─ kube-apiserver fetches JWKS from Authentik to verify signature
                           └─ RBAC: oidc:kanmegnea ClusterRoleBinding
```

Three network hops all require explicit configuration:
- Mac → Authentik: Tailscale + minicloud CA
- Mac → k3s API: Tailscale subnet route + UFW on set-hog
- k3s API → Authentik JWKS: minicloud CA trusted by kube-apiserver

---

## kubeconfig (`~/.kube/config`)

```yaml
- name: minicloud-oidc
  context:
    cluster: minicloud   # server: https://10.0.0.2:6443
    user: oidc-user

- name: oidc-user
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      command: kubectl
      args:
        - oidc-login
        - get-token
        - --oidc-issuer-url=https://auth.10.0.0.200.nip.io/application/o/kubernetes/
        - --oidc-client-id=kubernetes
        - --oidc-extra-scope=groups
        - --oidc-extra-scope=profile        # ← required for preferred_username claim
        - --listen-address=localhost:8000
      interactiveMode: IfAvailable
```

The `profile` scope is mandatory — without it Authentik omits `preferred_username` from the JWT, which k3s rejects because `oidc-username-claim=preferred_username` is set.

---

## k3s Configuration (`/etc/rancher/k3s/config.yaml` on set-hog)

```yaml
kube-apiserver-arg:
  - "oidc-issuer-url=https://auth.10.0.0.200.nip.io/application/o/kubernetes/"
  - "oidc-ca-file=/etc/rancher/k3s/minicloud-ca.crt"    # ← required
  - "oidc-client-id=kubernetes"
  - "oidc-username-claim=preferred_username"
  - "oidc-username-prefix=oidc:"
  - "oidc-groups-claim=groups"
  - "oidc-groups-prefix=oidc:"
```

The CA file must be copied to set-hog before use:

```bash
scp ~/minicloud-ca.crt set-hog:/tmp/minicloud-ca.crt
ssh set-hog "sudo cp /tmp/minicloud-ca.crt /etc/rancher/k3s/minicloud-ca.crt"
sudo systemctl restart k3s
```

---

## Authentik OAuth2 Provider

The `kubernetes` provider must have an RSA signing key set. Without one, Authentik signs JWTs with the `client_secret` using HS256, which kubelogin and k3s both reject.

**Fix via Django ORM:**

```bash
kubectl exec -n authentik deploy/authentik-server -- ak shell -c "
from authentik.providers.oauth2.models import OAuth2Provider
from authentik.crypto.models import CertificateKeyPair
p = OAuth2Provider.objects.get(name='kubernetes')
p.signing_key = CertificateKeyPair.objects.get(name='authentik Internal JWT Certificate')
p.save()
print('signing_key:', p.signing_key.name)
"
```

**Verify the JWKS now returns an RS256 key:**

```bash
/usr/bin/curl --cacert ~/minicloud-ca.crt -s \
  https://auth.10.0.0.200.nip.io/application/o/kubernetes/jwks/ \
  | python3 -m json.tool | grep alg
# → "alg": "RS256"
```

---

## UFW Rules on All Cluster Nodes

kubectl from the Mac reaches `10.0.0.2:6443` via Tailscale subnet routing. The controller advertises the `10.0.0.0/24` subnet, so Mac traffic arrives at each node with a Tailscale source IP in the `100.64.0.0/10` CGNAT range.

Every node's UFW only had `allow from 10.0.0.0/24`. This silently dropped TCP connections from `100.x.x.x` (ICMP was still allowed by UFW defaults, so ping worked but kubectl timed out).

**Applied to all 5 nodes:**

```bash
for node in set-hog fast-skunk fast-heron star-kitten swift-mac; do
  ssh $node "sudo ufw allow from 100.64.0.0/10"
done
```

**Verify:**

```bash
ssh set-hog "sudo ufw status"
# To                         Action      From
# Anywhere                   ALLOW       10.0.0.0/24
# Anywhere                   ALLOW       100.64.0.0/10    ← new
```

---

## The Four Root Causes

This section documents each failure in the order they were discovered, from outermost to innermost layer.

### Root Cause 1 — Authentik signing HS256 instead of RS256

**Symptom:** Chrome pop-up opened on every `kubectl` call. Token was obtained from Authentik but immediately rejected.

**Error in kubelogin:**
```
authentication error: authorization code flow error: could not verify the ID token:
oidc: malformed jwt: unexpected signature algorithm "HS256"; expected ["RS256"]
```

**Root cause:** `OAuth2Provider.signing_key = None` → Authentik falls back to signing with `client_secret` via HMAC-SHA256. OIDC spec requires public-key algorithms for verifiable tokens. kubelogin and k3s both enforce RS256.

**Fix:** Set `signing_key` to the "authentik Internal JWT Certificate" RSA keypair via Django ORM (see above). The JWKS endpoint (`/application/o/kubernetes/jwks/`) then exposes the RSA public key with `"alg": "RS256"`.

**Detection:** Decode the JWT header (first base64 segment):
```bash
token=$(cat ~/.kube/cache/oidc-login/*.json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['id_token'])")
echo $token | cut -d. -f1 | base64 -d 2>/dev/null | python3 -m json.tool | grep alg
```

---

### Root Cause 2 — UFW blocking Tailscale source IPs

**Symptom:** After HS256 was fixed, `kubectl` timed out with:
```
dial tcp 10.0.0.2:6443: i/o timeout
```
Ping to `10.0.0.2` worked (ICMP allowed), but TCP to port 6443 was silently dropped.

**Root cause:** UFW on set-hog had a single rule: `ALLOW from 10.0.0.0/24`. Mac Tailscale traffic arrives at set-hog with source IP `100.70.x.x` (Tailscale CGNAT), which doesn't match — UFW drops it with no response, causing TCP timeout rather than reset.

**Detection:**
```bash
nc -zv -G 5 10.0.0.2 6443   # times out from Mac
ssh set-hog "curl -sk https://10.0.0.2:6443/healthz"   # works from controller
ssh set-hog "sudo ufw status"   # shows only 10.0.0.0/24 rule
```

**Fix:** `sudo ufw allow from 100.64.0.0/10` on each node. Applied to all 5 in parallel.

---

### Root Cause 3 — k3s kube-apiserver can't verify OIDC JWKS (CA not trusted)

**Symptom:** After UFW was fixed, `kubectl` reached the API server but returned:
```
the server has asked for the client to provide credentials
```
k3s logs:
```
oidc authenticator: initializing plugin: Get "https://auth.10.0.0.200.nip.io/...":
tls: failed to verify certificate: x509: certificate signed by unknown authority
```

**Root cause:** kube-apiserver makes HTTPS requests to Authentik to fetch the discovery document and JWKS. The `auth.10.0.0.200.nip.io` endpoint serves a cert signed by the minicloud CA, which is not in set-hog's system cert pool. Every token was rejected because the signature could never be verified.

**Diagnostic check:**
```bash
ssh set-hog "curl -sv https://auth.10.0.0.200.nip.io/application/o/kubernetes/jwks/ 2>&1 | grep -E 'SSL|issuer|error'"
# → SSL certificate problem: unable to get local issuer certificate
```

**Fix:** Copy the minicloud CA to set-hog and add `oidc-ca-file` to k3s config:
```bash
scp ~/minicloud-ca.crt set-hog:/tmp/minicloud-ca.crt
ssh set-hog "sudo cp /tmp/minicloud-ca.crt /etc/rancher/k3s/minicloud-ca.crt"
# Add to /etc/rancher/k3s/config.yaml:
# kube-apiserver-arg:
#   - "oidc-ca-file=/etc/rancher/k3s/minicloud-ca.crt"
ssh set-hog "sudo systemctl restart k3s"
```

---

### Root Cause 4 — `preferred_username` claim absent from JWT

**Symptom:** After the CA was trusted, `kubectl` still returned 401. k3s logs:
```
Unable to authenticate the request: oidc: parse username claims "preferred_username": claim not present
```

**Root cause:** kubelogin was requesting `scope=groups openid`. The `preferred_username` claim is part of the `profile` scope in OIDC. Without `profile` in the scope request, Authentik omits `preferred_username` from the JWT. k3s was configured with `oidc-username-claim=preferred_username` — so every token was structurally valid but contained no usable username.

**Detection:**
```bash
# Decode the cached JWT payload
python3 -c "
import base64, json
token = open(list(__import__('glob').glob(
    __import__('os').path.expanduser('~/.kube/cache/oidc-login/*.json')
  ))[0]).read()
payload = json.loads(token)['id_token'].split('.')[1]
payload += '=' * (4 - len(payload) % 4)
data = json.loads(base64.urlsafe_b64decode(payload))
print('preferred_username' in data, data.get('preferred_username'))
print('groups' in data, data.get('groups'))
"
# → False None   (claim absent)
```

**Fix:** Add `--oidc-extra-scope=profile` to the `oidc-user` exec args in `~/.kube/config`. Delete the stale cache to force a fresh token:
```bash
rm ~/.kube/cache/oidc-login/*
kubectl --context minicloud-oidc get nodes   # triggers fresh browser login
```

---

## Verification Checklist (new machine setup)

```bash
# 1. Tailscale connected
ping -c 1 100.88.123.8

# 2. k3s API reachable via Tailscale subnet route
nc -zv -G 5 10.0.0.2 6443

# 3. Authentik JWKS returns RS256
/usr/bin/curl --cacert ~/minicloud-ca.crt -s \
  https://auth.10.0.0.200.nip.io/application/o/kubernetes/jwks/ \
  | python3 -m json.tool | grep alg

# 4. Full OIDC login
kubectl --context minicloud-oidc get nodes
# → browser opens once, then cached silently

# 5. Verify token has preferred_username
python3 -c "
import base64, json, glob, os
f = glob.glob(os.path.expanduser('~/.kube/cache/oidc-login/*.json'))
if not f: print('no cache'); exit()
payload = json.loads(open(f[0]).read())['id_token'].split('.')[1]
payload += '=' * (4 - len(payload) % 4)
d = json.loads(base64.urlsafe_b64decode(payload))
print('user:', d.get('preferred_username'))
print('groups:', d.get('groups'))
"
```

---

## Token Lifecycle

| Event | What happens |
|---|---|
| First login | Browser opens, user authenticates with TOTP, token cached at `~/.kube/cache/oidc-login/` |
| Subsequent calls | kubelogin reads cache, checks expiry, presents token silently |
| Access token expired | kubelogin uses refresh token to obtain new tokens silently (no browser) |
| Refresh token expired | kubelogin opens browser again (typically after days/weeks depending on Authentik session policy) |
| `signing_key` changed in Authentik | All cached tokens are invalidated — delete cache and re-login |
