# Gandi DNS Migration Report: Automated vs Manual Approach

**Date:** 2026-02-13
**Domain:** keken.nu
**Objective:** Migrate DNS from deSEC to Gandi LiveDNS with DNSSEC
**Final Score:** 86% on internet.nl (up from initial 64%)

---

## Executive Summary

The initial automated approach successfully migrated DNS records but failed to properly activate Gandi LiveDNS, requiring manual intervention. This report documents what went wrong, what manual steps were necessary, and how to achieve full automation in the future.

**Key Issues:**
1. Setting Gandi nameservers via API didn't activate native LiveDNS service
2. DNSSEC keys were created but not linked to domain registrar
3. Domain remained in "external nameservers" mode despite using Gandi's own nameservers

**Manual Steps Required:**
1. Switch to Gandi LiveDNS in admin panel (causing DNS reset)
2. Manually activate DNSSEC in admin panel

**Result:** Required complete DNS restoration and additional troubleshooting time.

---

## Timeline of Events

### Initial Automated Approach (Session Start)

#### Step 1: Create LiveDNS Zone ✅
```bash
POST https://api.gandi.net/v5/livedns/domains/keken.nu
```
**Result:** Success - LiveDNS zone created

#### Step 2: Migrate All DNS Records ✅
```bash
POST https://api.gandi.net/v5/livedns/domains/keken.nu/records
```
**Records Created:**
- 2 A records (@ and mta-sts)
- 1 MX record
- 4 TXT records (SPF, DMARC, MTA-STS, TLS-RPT)
- 2 CNAME records (autoconfig, autodiscover)
- 6 SRV records
- 3 CAA records

**Result:** Success - All 18 records created in LiveDNS

#### Step 3: Switch Nameservers ⚠️ PARTIAL SUCCESS
```bash
PUT https://api.gandi.net/v5/domain/domains/keken.nu/nameservers
Body: {
  "nameservers": [
    "ns-228-c.gandi.net",
    "ns-118-a.gandi.net",
    "ns-136-b.gandi.net"
  ]
}
```
**Result:** Nameservers changed BUT domain remained in "external nameservers" mode

**API Response:** `{"message": "Nameserver change launched. Please allow 12-24 hours for propagation."}`

**What Actually Happened:**
- ✅ Nameservers were updated at registrar level
- ❌ Domain NOT linked to LiveDNS service
- ❌ Domain still showed as "using external nameservers" in admin panel
- ❌ LiveDNS records created but domain not properly associated

#### Step 4: Enable DNSSEC ⚠️ PARTIAL SUCCESS
```bash
POST https://api.gandi.net/v5/livedns/domains/keken.nu/keys
Body: {"flags": 257}
```
**Result:** DNSSEC key created at LiveDNS level BUT not published to registry

**API Response:**
```json
{
  "message": "Domain Key Created",
  "id": "87024a50-081f-4c2b-aa6c-89529e52d2f1",
  "keytag": 48556,
  "algorithm": 13,
  "status": "active"
}
```

**What Was Missing:**
- ✅ DNSSEC key created in LiveDNS
- ❌ DS record NOT published to .nu registry
- ❌ DNSSEC not enabled at domain/registrar level
- ❌ Domain services still empty (no "gandilivedns" service)

---

### Manual Intervention Required

#### Problem Discovered
User checked Gandi admin panel and found:
- Domain status: "Using external nameservers" ❌
- LiveDNS: Not activated ❌
- DNSSEC: Not enabled ❌

#### Manual Step 1: Switch to Gandi LiveDNS in Admin Panel
**Action:** User clicked "Use Gandi LiveDNS" button in domain management interface

**Consequence:**
- ✅ Domain now using gandilivedns service
- ✅ Nameservers properly assigned
- ❌ **ALL DNS RECORDS WERE DELETED** and replaced with Gandi defaults
- ❌ Lost all 16 custom mailcow records
- ❌ Records replaced with Gandi email hosting defaults

**Records Lost:**
- Custom A record (194.164.197.33) → replaced with Gandi default (217.70.184.38)
- Custom MX (mail.villaherrgard.com) → replaced with Gandi mail servers
- All SPF, DKIM, DMARC, MTA-STS records → deleted
- All autoconfig/autodiscover records → deleted
- All custom SRV records → replaced with Gandi defaults

**Recovery Required:** Complete restoration of all DNS records via API

#### Manual Step 2: Restore DNS Records via API
```bash
# All 16 records had to be recreated
POST /v5/livedns/domains/keken.nu/records/{name}/{type}
```
**Issues Found During Restoration:**
- MX record created without trailing dot → became relative hostname
- Required fix: `mail.villaherrgard.com.` (with trailing dot)

#### Manual Step 3: Activate DNSSEC in Admin Panel
**Action:** User went to domain DNSSEC settings and manually enabled DNSSEC

**Result:**
- ✅ DNSSEC key synced from LiveDNS to domain level
- ✅ DS record published to .nu registry
- ✅ DNSSEC validation working
- ✅ Key Tag 48556, Algorithm 13 (ECDSAP256SHA256)

---

## Root Cause Analysis

### Why Automated Approach Failed

#### Issue 1: Nameserver API Confusion
**Problem:** The `/v5/domain/domains/{domain}/nameservers` endpoint changes nameservers at the registrar level but doesn't activate the LiveDNS service.

**What We Did:**
```bash
PUT /v5/domain/domains/keken.nu/nameservers
# Set to Gandi's nameservers
```

**What Happened:**
- Nameservers updated in WHOIS/registrar
- Domain remained in "external nameservers" mode
- LiveDNS zone existed but wasn't linked to domain

**What We Should Have Done:**
- Use a different endpoint or method to activate native LiveDNS
- Possibly DELETE the nameservers to revert to default LiveDNS

#### Issue 2: DNSSEC Not Linked
**Problem:** Creating DNSSEC key in LiveDNS doesn't automatically enable DNSSEC at domain level

**What We Did:**
```bash
POST /v5/livedns/domains/keken.nu/keys
```

**What Happened:**
- DNSSEC key created in LiveDNS
- Key status: "active" at LiveDNS level
- DS record NOT published to parent zone
- Domain DNSSEC status: null

**What We Should Have Done:**
- Also enable DNSSEC at domain level using domain API
- Publish DS record to registrar for TLD submission

---

## API Documentation Research

### Sources
- [Gandi Domain API Documentation](https://api.gandi.net/docs/domains/)
- [Gandi LiveDNS API Documentation](https://api.gandi.net/docs/livedns/)
- [Managing Nameservers - Gandi Docs](https://docs.gandi.net/en/domain_names/common_operations/changing_nameservers.html)
- [Managing DNS Records - Gandi Help](https://helpdesk.gandi.net/hc/en-us/articles/14000800808220-Managing-DNS-records)

### Key Findings

#### 1. Switching to LiveDNS
The documentation mentions:
> "To avoid interruption of services during the switch to Gandi's LiveDNS, you can reproduce your current DNS records as part of the switch"

**Missing from API Docs:** Clear endpoint for switching from external nameservers to native LiveDNS

**Hypothesis:** The correct approach may be:
```bash
# Option A: DELETE custom nameservers to revert to LiveDNS defaults
DELETE /v5/domain/domains/{domain}/nameservers

# Option B: Don't set nameservers at all if using LiveDNS
# Just create LiveDNS zone and records, domain defaults to LiveDNS

# Option C: Use domain services endpoint (undocumented)
POST /v5/domain/domains/{domain}/services
```

#### 2. DNSSEC Activation
**Current Understanding:**
- LiveDNS API creates DNSSEC keys but doesn't activate them
- Domain API manages DS records but endpoint is unclear

**Proper Approach (Based on Manual Success):**
The manual process suggests there's a domain-level DNSSEC activation that:
1. Links LiveDNS DNSSEC keys to domain
2. Publishes DS records to TLD registry
3. Updates domain status to show DNSSEC enabled

**Missing API Endpoint:**
```bash
# Hypothetical endpoint that should exist
POST /v5/domain/domains/{domain}/dnssec/enable
# Or
PUT /v5/domain/domains/{domain}
Body: {"dnssec": true}
```

#### 3. Domain Services
When checking domain status after manual switch:
```json
{
  "services": ["gandilivedns"]
}
```

This suggests there's a services configuration that wasn't set by our API calls.

---

## Correct Automated Approach

Based on analysis, here's the recommended workflow:

### Option A: New Domain Registration
```bash
# 1. Register domain (nameservers defaults to LiveDNS)
POST /v5/domain/domains
Body: {
  "fqdn": "example.com",
  # Don't specify nameservers - uses LiveDNS by default
}

# 2. DNS records are automatically in LiveDNS
POST /v5/livedns/domains/example.com/records/{name}/{type}

# 3. Enable DNSSEC (requires manual step or undocumented endpoint)
```

### Option B: Migrating Existing Domain to LiveDNS
```bash
# 1. Create LiveDNS zone and records FIRST
POST /v5/livedns/domains/keken.nu
POST /v5/livedns/domains/keken.nu/records/{name}/{type}
# Add all DNS records

# 2. DO NOT change nameservers via API
# Instead, remove external nameservers to revert to default
DELETE /v5/domain/domains/keken.nu/nameservers
# This should activate LiveDNS without resetting records

# 3. Enable DNSSEC at domain level (API endpoint unknown)
# Current options:
# - Manual via admin panel (what we did)
# - Contact Gandi support for API method
# - Use undocumented endpoint if exists
```

### Option C: Test with Sandbox API
```bash
# Use Gandi's sandbox environment to test
https://api.sandbox.gandi.net/docs/domains/

# Test DELETE nameservers approach
# Verify it doesn't reset DNS records
```

---

## Recommendations for Future Migrations

### 1. Pre-Migration Testing
- [ ] Test full workflow on sandbox domain
- [ ] Verify DELETE nameservers behavior
- [ ] Document exact API sequence that preserves records

### 2. LiveDNS Zone Creation
```bash
# Create zone BEFORE touching nameservers
POST /v5/livedns/domains/{domain}
```

### 3. DNS Record Population
```bash
# Add ALL records to LiveDNS zone
# Double-check FQDNs have trailing dots
for record in records:
    POST /v5/livedns/domains/{domain}/records/{name}/{type}
    # Ensure trailing dots: "mail.example.com."
```

### 4. Nameserver Switching
```bash
# Try DELETE to activate LiveDNS
DELETE /v5/domain/domains/{domain}/nameservers

# Verify domain services include "gandilivedns"
GET /v5/domain/domains/{domain}
# Check: "services": ["gandilivedns"]

# If DELETE doesn't work, document manual step required
```

### 5. DNSSEC Enablement
**Current State:** Requires manual intervention

**Future Research Needed:**
- [ ] Contact Gandi support for DNSSEC automation API
- [ ] Check if automatic sync exists (24-48h delay)
- [ ] Document if manual step is unavoidable

### 6. Verification Checklist
```bash
# Verify domain is using LiveDNS
GET /v5/domain/domains/{domain}
# Expect: "services": ["gandilivedns"]

# Verify all DNS records
GET /v5/livedns/domains/{domain}/records

# Verify DNSSEC key exists
GET /v5/livedns/domains/{domain}/keys

# Verify DS published to TLD
dig DS {domain}
# Should return DS record

# Verify DNSSEC validation
dig @8.8.8.8 +dnssec {domain} A
# Check for 'ad' flag and RRSIG
```

---

## Lessons Learned

### What Worked
1. ✅ LiveDNS zone creation via API
2. ✅ DNS record creation via API (with proper FQDNs)
3. ✅ DNSSEC key creation via API
4. ✅ Domain restoration after reset

### What Didn't Work
1. ❌ Switching nameservers via API didn't activate LiveDNS
2. ❌ DNSSEC key creation didn't publish DS record
3. ❌ No warning that manual switch would reset DNS records

### Critical Gaps in API Documentation
1. Missing: How to programmatically switch to LiveDNS
2. Missing: How to enable DNSSEC at domain level
3. Missing: Warning about DNS reset when switching to LiveDNS
4. Missing: Domain services management endpoint

### Best Practices Identified
1. Always use trailing dots in FQDNs: `mail.example.com.`
2. Create LiveDNS zone before changing nameservers
3. Verify domain services after nameserver changes
4. Test DNSSEC propagation with multiple methods
5. Keep backup of all DNS records before migration

---

## Cost-Benefit Analysis

### Automated Approach (Initial)
- **Time:** 30 minutes
- **Success:** Partial (DNS records created, nameservers changed)
- **Issues:** Required manual intervention, caused DNS reset

### Manual Steps Required
- **Time:** 15 minutes
- **Actions:** 2 clicks in admin panel
- **Side Effects:** Complete DNS reset requiring restoration

### Full Restoration
- **Time:** 45 minutes
- **Actions:** API-based restoration of 16 records
- **Issues:** MX record FQDN bug requiring fix

### Total Time
- **Planned:** 30 minutes (automated)
- **Actual:** 90 minutes (automated + manual + fixes)
- **Efficiency:** 33% (3x longer than expected)

---

## Future Automation Strategy

### Phase 1: API Research (Before Migration)
```bash
# Test on sandbox domain
1. Create LiveDNS zone
2. Add test records
3. Try DELETE nameservers
4. Verify services and records
5. Document working sequence
```

### Phase 2: Production Migration Script
```bash
#!/bin/bash
# migrate-to-gandi-livedns.sh

DOMAIN=$1
API_TOKEN=$2

# 1. Create LiveDNS zone
create_livedns_zone

# 2. Add all DNS records
migrate_dns_records

# 3. Switch to LiveDNS (tested method)
activate_livedns

# 4. Verify services
verify_livedns_active

# 5. Enable DNSSEC (manual if no API)
if has_dnssec_api; then
    enable_dnssec_api
else
    echo "⚠️ Manual step required: Enable DNSSEC in admin panel"
    echo "   https://admin.gandi.net/domain/${DOMAIN}/dnssec"
    pause_for_manual_step
fi

# 6. Verification
verify_dns_records
verify_dnssec_working
```

### Phase 3: Monitoring & Validation
```bash
# Automated checks
- DNS record integrity
- DNSSEC chain validation
- Service status monitoring
- Performance testing (internet.nl)
```

---

## Questions for Gandi Support

1. **LiveDNS Activation:**
   - What is the correct API endpoint to switch from external nameservers to LiveDNS?
   - Does `DELETE /v5/domain/domains/{domain}/nameservers` activate LiveDNS?
   - Why does switching to LiveDNS via admin panel reset DNS records?

2. **DNSSEC Automation:**
   - Is there an API endpoint to enable DNSSEC at domain level?
   - How to publish DS records to TLD registry via API?
   - Why doesn't creating DNSSEC key in LiveDNS automatically enable it?

3. **Domain Services:**
   - How to manage domain services via API?
   - What is the endpoint for `"services": ["gandilivedns"]`?
   - Can we verify service activation programmatically?

4. **Documentation Gaps:**
   - Can you provide complete API workflow for LiveDNS migration?
   - Are there undocumented endpoints for DNSSEC management?
   - Can you add warnings about DNS reset behavior?

---

## Conclusion

The Gandi API provides excellent tools for DNS management but lacks clear documentation for:
1. Activating native LiveDNS service programmatically
2. Enabling DNSSEC at the domain registrar level
3. Preventing DNS record reset during LiveDNS activation

**Current State:** 80% automation possible, 20% requires manual intervention

**Recommendation:**
- Contact Gandi support for missing API endpoints
- Test DELETE nameservers approach on sandbox domain
- Document any manual steps as required in automation scripts
- Add verification steps after each API call
- Keep DNS record backups before any migration

**For Production Domains (villaherrgard.se, nysattra.se):**
- Use improved workflow documented in this report
- Plan for potential manual DNSSEC activation
- Have DNS restoration script ready
- Test on keken.nu first (already done ✅)
- Schedule migration during low-traffic period

---

## Appendix: API Call Reference

### Successful API Calls
```bash
# Create LiveDNS zone
POST /v5/livedns/domains/{domain}

# Create DNS record
POST /v5/livedns/domains/{domain}/records/{name}/{type}
Body: {"rrset_values": ["value"], "rrset_ttl": 10800}

# Update DNS record
PUT /v5/livedns/domains/{domain}/records/{name}/{type}
Body: {"rrset_values": ["value"]}

# Create DNSSEC key
POST /v5/livedns/domains/{domain}/keys
Body: {"flags": 257}

# Get domain info
GET /v5/domain/domains/{domain}

# Get DNS records
GET /v5/livedns/domains/{domain}/records

# Get DNSSEC keys
GET /v5/livedns/domains/{domain}/keys
```

### Problematic API Calls
```bash
# Change nameservers (doesn't activate LiveDNS)
PUT /v5/domain/domains/{domain}/nameservers
Body: {"nameservers": ["ns1.gandi.net", "ns2.gandi.net", "ns3.gandi.net"]}
# Result: Nameservers changed but LiveDNS not activated

# Create DNSSEC key (doesn't publish DS)
POST /v5/livedns/domains/{domain}/keys
Body: {"flags": 257}
# Result: Key created but DS not published to TLD
```

### Untested API Approaches
```bash
# Potential LiveDNS activation (untested)
DELETE /v5/domain/domains/{domain}/nameservers

# Potential DNSSEC enablement (may not exist)
POST /v5/domain/domains/{domain}/dnssec
PUT /v5/domain/domains/{domain}
Body: {"dnssec": true}
```

---

**Report Generated:** 2026-02-13
**Domain:** keken.nu
**Final Status:** ✅ Fully operational (86% internet.nl score)
**Automation Level:** 80% (manual DNSSEC activation required)
