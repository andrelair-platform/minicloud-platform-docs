---
slug: hybrid-cloud-bare-metal-cloudflare
title: "Bare Metal First, Cloud at the Edge — Our Hybrid Architecture Decision"
authors: [andrelair]
tags: [kubernetes, bare-metal, hybrid-cloud, cloudflare, aws, architecture, devops, infrastructure, k3s, self-hosted]
date: 2026-08-09
description: "Most tutorials teach you to deploy on AWS. We went the other way: five bare-metal nodes on the floor, Cloudflare at the edge, and cloud services only where physics makes self-hosting impossible. This is why."
---

Most Kubernetes tutorials start with `eksctl create cluster` or `gcloud container clusters create`. A managed control plane, auto-scaling node groups, load balancers that appear with a single annotation. The cloud abstracts the hardware entirely.

We went the other direction. Five physical machines — four ThinkPad laptops and a 2012 MacBook Pro — running k3s, with every workload scheduled and operated by us. No managed control plane. No auto-scaling node group. No cloud load balancer. Just Linux, containerd, and Flannel on iron we can touch.

But we do use cloud services. AWS delivers our email. Cloudflare sits in front of every HTTP request. A Lightsail instance relays our video call UDP traffic. Tailscale connects us to the cluster from anywhere.

This post explains how we decided what goes where, and why the resulting architecture is not a compromise — it is a deliberate design.

{/* truncate */}

## The Starting Question

When you run infrastructure, every service you add forces the same question: does this run on my hardware, or does it run somewhere else?

The naive answer is "it depends." The useful answer requires a framework. Ours has three criteria:

1. **Does it require a public IP or a specific network position that I cannot provide?**
2. **Would running it myself damage something I cannot fix — like email deliverability reputation?**
3. **Is the operational cost of running it myself disproportionate to the benefit?**

If the answer to any of these is yes, the service belongs in the cloud. Otherwise, it runs on our nodes.

Let us apply this to every service on the platform.

---

## What Runs On-Premise

Everything with a yes answer to "can we run this ourselves without a structural disadvantage" runs on the cluster.

```
┌─────────────────────────────────────────────────────────────────────┐
│  k3s cluster — 5 nodes, bare metal                                  │
│                                                                     │
│  set-hog (control plane)    fast-skunk    fast-heron                │
│  star-kitten                swift-mac (MacBook Pro 2012)            │
│                                                                     │
│  Workloads (selected):                                              │
│  ArgoCD · Authentik · Harbor · Grafana · Loki · Tempo               │
│  Backstage · Plane · ERPNext · Matrix · Element · Jitsi             │
│  Stalwart mail · Open WebUI · Vaultwarden · Vault                   │
│  LiteLLM · vLLM · Flowise · MLflow · n8n · Temporal                │
│  Longhorn storage · MinIO · PostgreSQL · MariaDB                    │
└─────────────────────────────────────────────────────────────────────┘
```

This is twenty-five production workloads, all their databases, all their storage — running on hardware that costs nothing per month to operate beyond electricity. It is also where every piece of sensitive data lives: insurance policy records, employee HR data, authentication credentials, vector embeddings, LLM inference.

The data sovereignty dimension matters here more than cost. Running a French insurance information system means operating under GDPR and ACPR supervision. Every byte of PII staying inside physical hardware we control, in a jurisdiction we chose, is a compliance decision as much as an infrastructure one.

---

## What Runs In the Cloud, and Why

### Cloudflare — The Edge Layer

The cluster sits behind a home internet connection. Home ISPs assign dynamic IP addresses, often share IPs across customers, and do not provide the DDoS mitigation or the BGP peering that makes a public endpoint reliable. Cloudflare solves all of this.

**Cloudflare Tunnel** is the core mechanism. Rather than exposing our cluster's IP address to the internet, we run a lightweight `cloudflared` daemon on the controller. It maintains an outbound connection to Cloudflare's edge. When a request arrives for `argocd.devandre.sbs`, Cloudflare routes it through that tunnel to our internal service — without our IP ever being published.

```
External request → argocd.devandre.sbs
                        │
                        ▼
          Cloudflare edge (WAF + DDoS mitigation)
                        │
                   Cloudflare Tunnel
                        │
                        ▼
          cloudflared daemon (controller, 100.88.123.8)
                        │
                        ▼
          ArgoCD service (argocd namespace, 10.0.0.200)
```

Every one of our twenty-three public endpoints follows this path. The WAF inspects traffic before it reaches the cluster. DDoS traffic is absorbed at Cloudflare's edge, not by our nodes. The origin IP is never exposed.

**Cloudflare R2** stores our off-site backup. Velero backs up cluster state to an on-cluster MinIO instance daily. A separate weekly schedule writes to R2. If the physical hardware is destroyed — fire, flood, theft — the cluster state survives in R2 and can be restored to any Kubernetes cluster. This is the one scenario where on-premise storage structurally cannot help: the backup must survive the loss of the site.

**The cost:** Cloudflare Tunnel is free. R2 is free up to 10 GB storage and 1 million Class A operations per month. Our weekly backup runs well within this. Cloudflare WAF on the free plan covers the essential rules. Total monthly spend: zero.

---

### AWS SES — Email Delivery

Stalwart Mail runs on the cluster and handles all inbound and outbound email for `devandre.sbs`. For inbound, this works perfectly — Stalwart receives, parses, and stores mail entirely on-premise.

For outbound, running your own SMTP relay is structurally disadvantaged. IP reputation is everything in email deliverability. A home IP address has no sender reputation — it will be classified as residential and rejected or filtered by most major providers. Warming a new IP takes months. If the IP is ever shared with a spam source, the reputation follows the IP, not the sender.

AWS SES solves this. It provides a sending infrastructure with established IP reputation, DKIM signing, SPF alignment, and DMARC support. Our email originates in Stalwart, routes through SES as a relay, and arrives with the deliverability profile of a commercial sending platform.

The cost is $0.10 per thousand messages. For the volume of a small insurance company's transactional email — policy confirmations, claim updates, dunning notices, alerts — the monthly spend is cents.

This satisfies criterion 2 precisely: running it ourselves would damage email deliverability in a way we cannot fix without months of IP warming and without certainty of outcome.

---

### AWS Lightsail — TURN Relay for Video

Jitsi Meet runs on the cluster. Most video calls work peer-to-peer or through the Jitsi Videobridge (JVB) running on `star-kitten`. But WebRTC peer-to-peer fails when both participants are behind symmetric NAT — which is common on mobile networks and corporate firewalls.

The solution is a TURN server: a relay that both participants can reach directly, which forwards UDP packets between them. A TURN server must be reachable on public UDP ports without NAT. It must have a stable public IP.

Our cluster sits behind NAT. We cannot expose arbitrary UDP ports reliably without a fixed public IP and control over the router. A Lightsail instance at $3.50/month solves this cleanly: static IP, public UDP ports, coturn running as a service.

This satisfies criterion 1. The TURN server requires a network position — public UDP reachability without NAT — that we structurally cannot provide from within the cluster.

---

### Tailscale — Zero-Trust VPN

The cluster is not directly reachable from the internet (by design — Cloudflare Tunnel handles HTTP). But the controller needs to be reachable for SSH, for kubectl, and for infrastructure operations.

Tailscale provides this via WireGuard-based mesh networking. Every node gets a Tailscale address in the `100.x.x.x` range. The controller is reachable at `100.88.123.8` from any device on the same Tailscale network. The data plane is peer-to-peer; no traffic flows through Tailscale's servers if a direct path exists.

The control plane is a SaaS service — Tailscale manages key distribution and device authentication. This is a deliberate trade-off: we do not want to operate the PKI and coordination service ourselves for a zero-trust overlay. The free plan covers up to 100 devices, which we will not exceed.

---

### GitHub — Source Control and CI

All code, GitOps manifests, and documentation live in GitHub. CI runs on GitHub Actions with runners provided by GitHub. This is a SaaS dependency, but it satisfies criterion 3: the operational cost of running self-hosted Gitea, a CI runner fleet, and a container scan pipeline ourselves would be disproportionate to the benefit when GitHub's free tier provides all of it.

The one deliberate decision here is that the container registry is **not** GitHub Container Registry. All images push to Harbor, running on the cluster, for two reasons: data locality (images are pulled from within the cluster, not over the internet) and control (we manage image retention, vulnerability scanning, and access control ourselves).

---

## The Decision Framework in Practice

Every time we add a new service, we apply the same three questions:

```
Does it require a public IP or specific network position?
    YES → cloud (Lightsail, EC2 free tier)
    NO  ↓

Would running it myself damage an irreplaceable reputation?
    YES → cloud (SES for email deliverability)
    NO  ↓

Is the operational overhead disproportionate to the benefit?
    YES → cloud SaaS (Tailscale, GitHub)
    NO  → on-premise (everything else)
```

This is why twenty-five workloads run on bare metal and four cloud services handle what bare metal cannot.

---

## The Cost Comparison

Running the equivalent of this platform on AWS would require:

| Component | AWS equivalent | Estimated monthly cost |
|---|---|---|
| 5 k8s worker nodes (2 vCPU, 8GB) | 5× t3.large EKS workers | ~$270 |
| Control plane | EKS managed | $72 |
| Storage (2TB total) | EBS gp3 | ~$160 |
| Object storage (MinIO equivalent) | S3 | ~$46 |
| Load balancer | ALB | ~$20 |
| NAT gateway | NAT GW | ~$32 |
| **Total** | | **~$600/month** |

Our actual cloud spend:

| Service | Monthly cost |
|---|---|
| AWS SES | ~$0.50 |
| AWS Lightsail (TURN) | $3.50 |
| Cloudflare | $0 |
| Tailscale | $0 |
| GitHub | $0 |
| **Total** | **~$4/month** |

The bare-metal nodes have a one-time acquisition cost (used ThinkPads, ~€200–400 each) and an ongoing electricity cost (approximately €15/month for 5 machines). The cluster cost is around €25/month all-in.

The architecture does not save money by being clever. It saves money by correctly identifying which problems require cloud infrastructure and which do not.

---

## What This Architecture Cannot Do

Honesty requires listing the trade-offs.

**No elastic scaling.** If traffic spikes beyond our five nodes' capacity, there is no auto-scaling group to add capacity. We scale vertically (more RAM in a ThinkPad) or accept that the cluster has a ceiling.

**No availability zone redundancy.** All five nodes are in the same physical location. A power outage, a fire, or a network failure takes everything down simultaneously. Cloudflare R2 backup and Velero give us data recovery, but RTO (recovery time) is measured in hours, not minutes.

**Higher operational burden.** When a node goes down, we fix it. When a disk fails, we replace it. When k3s releases a security patch, we plan and execute the upgrade. A managed Kubernetes service handles most of this automatically.

These are conscious trade-offs made for a specific context: a portfolio platform demonstrating full-stack infrastructure capability, where data sovereignty and operational control are more important than elastic scale or five-nines availability.

For a production insurance company at scale, the architecture would shift: on-premise for regulated data processing, cloud Kubernetes (EKS/AKS) for stateless workloads that need elastic capacity, with the same Cloudflare edge layer in front of both.

---

## The Principle

The question is never "cloud or on-premise." It is always "what does this specific workload require, and where does that place it?"

Our database workloads require data locality, consistent IOPS, and compliance control. They run on bare metal.

Our email delivery requires IP reputation that takes months to build. It runs through SES.

Our video relay requires a public UDP address without NAT. It runs on Lightsail.

Our public endpoints require DDoS mitigation and a stable origin address. They run through Cloudflare.

Everything else runs on the cluster.

That is hybrid cloud: not splitting workloads arbitrarily between environments, but placing each workload in the environment that structurally fits it. The cloud services we use cost four euros a month. The platform they front is twenty-five production workloads running on hardware on the floor.
