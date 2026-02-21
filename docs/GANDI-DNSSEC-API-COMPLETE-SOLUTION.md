# Complete Gandi DNSSEC API Solution

**Date:** 2026-02-13 (updated 2026-02-21)
**Status:** VALIDATED AND TESTED - 100% automation achieved

---

## The Two-Level DNSSEC Architecture

### Level 1: LiveDNS (Zone Signing)
**Endpoint:** `/v5/livedns/domains/{fqdn}/keys`

**Purpose:** Manages the actual DNSSEC keys that sign your DNS zone

**Operations:**
```bash
# List DNSSEC keys in LiveDNS
GET /v5/livedns/domains/{domain}/keys

# Create DNSSEC key in LiveDNS
POST /v5/livedns/domains/{domain}/keys
Body: {"flags": 257}

# Response provides:
{
  "fqdn": "keken.nu",
  "flags": 257,
  "algorithm": 13,
  "algorithm_name": "ECDSAP256SHA256",
  "ds": "keken.nu. 3600 IN DS 48556 13 2 91dff5...",
  "status": "active",
  "id": "..."
}
```

**What's Missing:** The actual `public_key` field! LiveDNS API only returns the DS digest.

---

### Level 2: Domain/Registry (Parent Zone Publication)
**Endpoint:** `/v5/domain/domains/{domain}/dnskeys`

**Purpose:** Publishes DNSSEC keys to the TLD registry (parent zone)

**Operations:**
```bash
# List keys published to registry
GET /v5/domain/domains/{domain}/dnskeys

# Publish key to registry
POST /v5/domain/domains/{domain}/dnskeys
Body: {
  "algorithm": 13,
  "type": "ksk",
  "public_key": "AicsHZhBpl0Hte9YRC2S0/IAzeE1SwQ+mqepvq3sU3rc2mZZ9l2h/ogBPIuDSZyTgtP6rKO33SmZNTJH+l27Ow=="
}

# Gandi calculates keytag and digest automatically
# Response:
{
  "algorithm": 13,
  "type": "ksk",
  "public_key": "AicsHZhB...",
  "keytag": 48556,
  "digest_type": 2,
  "digest": "91DFF53DD3C84FD...",
  "id": 1281080
}
```

**What's Required:** The BASE64-encoded public key (RDATA format)

---

## The Missing Link: Getting the Public Key

### The Problem

When you create a DNSSEC key via LiveDNS API:
1. ✅ LiveDNS creates the key pair (private + public)
2. ✅ LiveDNS provides the DS record (digest)
3. ❌ LiveDNS API does NOT expose the public key
4. ❌ Cannot POST to domain dnskeys without public key

### The Chicken-and-Egg

To enable DNSSEC via API, you need:
- Public key to POST to `/domain/.../dnskeys`
- But LiveDNS API doesn't provide it
- And DNS doesn't have DNSKEY until DNSSEC is enabled at domain level

### How to Get the Public Key

**Method 1: Query DNS (Once DNSSEC is Active)**
```bash
# After DNSSEC is enabled (manually or via previous setup)
dig @ns-64-a.gandi.net +short DNSKEY keken.nu

# Returns:
# 257 3 13 AicsHZhBpl0Hte9YRC2S0/IAzeE1SwQ+mqepvq3sU3rc2mZZ9l2h/ogB...
#          ^-- This is the public key

# Extract with:
dig +short DNSKEY keken.nu | grep "^257" | awk '{print $4}'
```

**Method 2: Manual Admin Panel (What You Did)**
- Gandi's web UI has access to the full key material
- Clicking "Enable DNSSEC" publishes the public key to domain level
- Creates the link between LiveDNS and registry

**Method 3: API Alternative (Theoretical)**
If LiveDNS API provided a `public_key` field in the response, we could:
```bash
# Create key at LiveDNS
POST /v5/livedns/domains/{domain}/keys
# Get public_key from response (currently not provided)

# Immediately publish to registry
POST /v5/domain/domains/{domain}/dnskeys
Body: {
  "algorithm": 13,
  "type": "ksk",
  "public_key": "{public_key_from_livedns}"
}
```

---

## ~~Why Manual Step Was Required~~ SOLVED (2026-02-21)

The original experiment (2026-02-13) concluded a manual step was needed because the DNSKEY
wasn't found in DNS after LiveDNS key creation. However, re-testing on 2026-02-21 revealed
the **DNSKEY is immediately available from Gandi's authoritative nameserver** after key creation:

```bash
# After POST /v5/livedns/domains/{domain}/keys:
dig @ns-64-a.gandi.net DNSKEY keken.nu +short
# Returns: 257 3 13 kpPMEPsmgDAADPd2Nbt4/VFbW+2R4OUjxUaFM3H1Pbq...
```

The original test likely queried a recursive resolver (e.g., 8.8.8.8) instead of Gandi's
authoritative nameserver directly, which is why the DNSKEY wasn't found.

**Key finding:** No manual step is required. The public key can be extracted from DNS and
POSTed to the domain dnskeys API to publish the DS record.

---

## Complete API Workflow (Validated 2026-02-21)

### Fully Automated -- Tested on keken.nu

```bash
#!/bin/bash
DOMAIN="keken.nu"
TOKEN="..."

# Step 1: Create LiveDNS zone and records
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "https://api.gandi.net/v5/livedns/domains/$DOMAIN"

# Add DNS records...

# Step 2: Activate LiveDNS service
# Setting Gandi nameservers activates the gandilivedns service.
# DNS records are NOT wiped (unlike the admin panel method).
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.gandi.net/v5/domain/domains/$DOMAIN/nameservers" \
  -d '{"nameservers": ["ns-64-a.gandi.net", "ns-90-b.gandi.net", "ns-58-c.gandi.net"]}'

# Step 3: Create DNSSEC key at LiveDNS
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.gandi.net/v5/livedns/domains/$DOMAIN/keys" \
  -d '{"flags": 257}'

# Step 4: Extract public key from Gandi authoritative nameserver
# DNSKEY is available immediately -- query Gandi's NS directly, not a recursive resolver.
PUBKEY=$(dig @ns-64-a.gandi.net DNSKEY $DOMAIN +short | grep "^257" | awk '{print $4$5}')

# Step 5: Publish DS record to TLD registry
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.gandi.net/v5/domain/domains/$DOMAIN/dnskeys" \
  -d "{
    \"algorithm\": 13,
    \"type\": \"ksk\",
    \"public_key\": \"$PUBKEY\"
  }"
```

**No blockers.** All 5 steps are fully automated via API + DNS query.

---

## Workaround for Production Migrations

### Option A: One-Time Manual Setup + Preservation

For domains that already have DNSSEC enabled:
1. Don't delete the DNSSEC key during migration
2. The existing domain-level dnskeys entry persists
3. Nameserver changes don't affect it (we learned this!)

**Workflow:**
```bash
# If DNSSEC already active on source:
# 1. Migrate DNS records to Gandi LiveDNS
# 2. Set Gandi nameservers (activates LiveDNS)
# 3. DNSSEC continues working (already linked)
# No manual step needed!
```

### Option B: Post-Migration DNSSEC Setup

For new domains or after DNSSEC was removed:
```bash
# 1. Complete DNS migration via API (95% automated)
# 2. Manual step: Enable DNSSEC in admin panel (1 click)
# 3. Wait 5-30 minutes for propagation
```

### Option C: Query-Then-Publish (For Re-Linking)

If you have DNSSEC active and need to re-link:
```bash
# 1. Ensure DNSSEC is enabled (keys in DNS)
# 2. Query DNSKEY from DNS
PUBKEY=$(dig +short DNSKEY $DOMAIN | grep "^257" | awk '{print $4}')

# 3. POST to domain dnskeys
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "https://api.gandi.net/v5/domain/domains/$DOMAIN/dnskeys" \
  -d "{
    \"algorithm\": 13,
    \"type\": \"ksk\",
    \"public_key\": \"$PUBKEY\"
  }"
```

**Caveat:** Only works if DNSSEC is already active and publishing DNSKEY

---

## Recommendation for Gandi

**Feature Request:**

Add `public_key` field to LiveDNS keys API response:

```json
// Current response
{
  "fqdn": "keken.nu",
  "flags": 257,
  "algorithm": 13,
  "ds": "keken.nu. 3600 IN DS 48556 13 2 91dff5...",
  "status": "active"
}

// Proposed enhancement
{
  "fqdn": "keken.nu",
  "flags": 257,
  "algorithm": 13,
  "public_key": "AicsHZhBpl0Hte9YRC2S0/IAzeE1SwQ+mqepvq3sU3rc2mZZ9l2h/ogB...",
  "ds": "keken.nu. 3600 IN DS 48556 13 2 91dff5...",
  "status": "active"
}
```

This would enable full DNSSEC automation via API.

---

## Impact on Production Workflow

### For villaherrgard.se and nysattra.se

**Current State (one.com):**
- DNSSEC status: Unknown (check before migration)

**Migration Scenario 1: No DNSSEC Currently**
```
Automation: 95%
Manual step: Enable DNSSEC after migration (1 click)
```

**Migration Scenario 2: DNSSEC Already Active**
```
Option A: Keep existing DNSSEC (if staying with one.com DNS)
  - Not applicable (migrating DNS to Gandi)

Option B: Migrate to Gandi DNSSEC
  - Automation: 95%
  - Manual: Enable DNSSEC at Gandi (1 click)
  - Brief DNSSEC outage during switch (acceptable)
```

**Migration Scenario 3: Want to Pre-Enable DNSSEC**
```
Possible workflow:
1. Add domain to Gandi (don't switch nameservers yet)
2. Enable DNSSEC at Gandi manually
3. Get DS record from Gandi
4. Add DS record to current DNS provider (one.com)
5. Wait for propagation
6. Switch nameservers to Gandi
7. Remove DS record from one.com
Result: Zero DNSSEC downtime
```

---

## Final Automation Assessment

**Automation Level: 100%** (validated 2026-02-21 on keken.nu)

✅ Fully Automated:
- DNS zone creation
- DNS record migration
- LiveDNS service activation (PUT nameservers with Gandi NS)
- DNSSEC key creation (POST to LiveDNS keys)
- DNSSEC registry publication (query DNSKEY from authoritative NS, POST to domain dnskeys)
- Verification and testing

⚠️ No manual steps required.

**Key discoveries (2026-02-21 retest):**
1. `PUT /v5/domain/domains/{domain}/nameservers` with Gandi NS **does** activate `gandilivedns` service (original test incorrectly concluded it didn't)
2. DNS records are **preserved** when switching nameservers via API (unlike the admin panel which wipes them)
3. DNSKEY record is **immediately queryable** from Gandi's authoritative nameserver after LiveDNS key creation
4. The public key extracted from DNS can be POSTed to `/v5/domain/domains/{domain}/dnskeys` to publish the DS record

---

## Conclusion

The two-level architecture is fully automatable:

1. **LiveDNS level** (`/livedns/.../keys`) - Zone signing (creates DNSKEY)
2. **Domain level** (`/domain/.../dnskeys`) - Parent publication (creates DS)

The bridge between them is `dig @ns-64-a.gandi.net DNSKEY {domain}` — this provides the
public key needed to POST to the domain API. No API gap, no manual step.

---

## References

- [Gandi LiveDNS API](https://api.gandi.net/docs/livedns/)
- [Gandi Domain API](https://api.gandi.net/docs/domains/)
- [DNSSEC at Gandi](https://docs.gandi.net/en/domain_names/advanced_users/dnssec.html)
- [DNSControl Issue #674](https://github.com/StackExchange/dnscontrol/issues/674)

---

**Status:** Fully validated with live test
**Automation Level:** 100%
**Production Ready:** ✅ Yes, zero manual steps
