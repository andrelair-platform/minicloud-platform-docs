---
id: maas-setup
title: MAAS Setup
sidebar_position: 6
---

# MAAS Setup

## Installation

```bash
sudo snap install maas
```

MAAS is distributed as a snap package — this installs the full stack (region controller, rack controller, UI).

---

## Verify Services

```bash
sudo maas status
```

All services should show `running`.

---

## Fix MAAS UI Binding (Critical)

If the MAAS UI returns a 502 error or is inaccessible:

```bash
sudo snap set maas url=http://10.0.0.1:5240/MAAS
sudo snap restart maas
```

This binds the MAAS API and UI to the correct network interface.

---

## Access the UI

```text
http://10.0.0.1:5240/MAAS
```

Default admin user: `maasadmin`

---

## Learn More

Official MAAS quickstart guide — covers the full provisioning flow in 30 minutes:

[MAAS in Thirty Minutes — Canonical Docs](https://canonical.com/maas/docs/maas-in-thirty-minutes)

---

## Initial Configuration Checklist

- [ ] Set DNS forwarder (e.g. `8.8.8.8`)
- [ ] Import Ubuntu 24.04 LTS image
- [ ] Enable DHCP on `10.0.0.0/24` fabric
- [ ] Disable DHCP on `192.168.1.0/24` fabric
- [ ] Delete IPv6 subnets
- [ ] Add SSH public key under user profile
