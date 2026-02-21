# Gandi LiveDNS Migration - Quick Reference

## Automated Workflow (Validated 2026-02-21)

The entire LiveDNS + DNSSEC setup is fully automatable via API. Zero manual steps.

### Step 1: Create LiveDNS zone and DNS records
```bash
# Create zone
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "https://api.gandi.net/v5/livedns/domains/$DOMAIN"

# Add records (repeat for each record)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.gandi.net/v5/livedns/domains/$DOMAIN/records" \
  -d '{"rrset_name": "@", "rrset_type": "MX", "rrset_ttl": 3600, "rrset_values": ["10 mail.villaherrgard.com."]}'
```

### Step 2: Activate LiveDNS
```bash
# Set Gandi nameservers -- this activates the gandilivedns service
# DNS records are preserved (NOT wiped like the admin panel method)
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.gandi.net/v5/domain/domains/$DOMAIN/nameservers" \
  -d '{"nameservers": ["ns-64-a.gandi.net", "ns-90-b.gandi.net", "ns-58-c.gandi.net"]}'
```

### Step 3: Enable DNSSEC
```bash
# Create DNSSEC key at LiveDNS level (starts zone signing)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.gandi.net/v5/livedns/domains/$DOMAIN/keys" \
  -d '{"flags": 257}'

# Extract public key from Gandi authoritative nameserver (available immediately)
PUBKEY=$(dig @ns-64-a.gandi.net DNSKEY $DOMAIN +short | grep "^257" | awk '{print $4$5}')

# Publish DS record to TLD registry
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.gandi.net/v5/domain/domains/$DOMAIN/dnskeys" \
  -d "{\"algorithm\": 13, \"type\": \"ksk\", \"public_key\": \"$PUBKEY\"}"
```

---

## What the Original Test Got Wrong (2026-02-13)

### "Problem 1: Nameserver API doesn't activate LiveDNS" -- WRONG

The original test used non-standard Gandi nameservers (`ns-228-c.gandi.net`). Using the
correct LiveDNS nameservers (`ns-64-a`, `ns-90-b`, `ns-58-c`) via PUT **does** activate
the `gandilivedns` service. Additionally, DNS records are preserved -- unlike the admin
panel "Use Gandi LiveDNS" button which wipes all records.

### "Problem 2: DNSSEC key not published" -- WRONG

The original test queried recursive resolvers for the DNSKEY record and didn't find it.
Querying Gandi's authoritative nameserver directly (`dig @ns-64-a.gandi.net DNSKEY domain`)
returns the DNSKEY immediately after key creation. The public key can then be POSTed to
the domain dnskeys API to publish the DS record.

---

## Key Lessons

### DO
- Create LiveDNS zone BEFORE switching nameservers
- Use trailing dots in FQDNs: `mail.example.com.`
- Query Gandi's authoritative NS (`ns-64-a.gandi.net`) for DNSKEY, not recursive resolvers
- Verify domain services after changes
- Keep backup of DNS records before migration

### DON'T
- Don't use the admin panel "Use Gandi LiveDNS" button (wipes DNS records)
- Don't query recursive resolvers (8.8.8.8) for DNSKEY immediately after creation
- Don't migrate production without testing workflow
- Don't skip verification steps

---

## Verification Checklist

```bash
# 1. Check LiveDNS is active
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.gandi.net/v5/domain/domains/$DOMAIN" | \
  jq '.services'
# Expected: ["gandilivedns"] or ["dnssec", "gandilivedns"]

# 2. Check DNS records preserved
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.gandi.net/v5/livedns/domains/$DOMAIN/records" | \
  jq 'length'
# Expected: record count matches pre-migration

# 3. Check DNSSEC key active
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.gandi.net/v5/livedns/domains/$DOMAIN/keys" | \
  jq '.[] | select(.deleted == false) | {status, algorithm_name}'
# Expected: status: "active"

# 4. Check DS record in TLD
dig DS $DOMAIN +short
# Expected: DS record with matching keytag

# 5. Check DNSSEC validation
dig @8.8.8.8 +dnssec $DOMAIN A | grep "flags.*ad"
# Expected: "ad" flag present
```

---

## For Next Migration (nysattra.se, villaherrgard.se, sono-vagnala.se)

### Recommended Workflow
1. Create LiveDNS zone via API
2. Add all DNS records via API
3. Set Gandi nameservers via API (activates LiveDNS, preserves records)
4. Create DNSSEC key via API
5. Query DNSKEY from authoritative NS, POST to domain dnskeys
6. Verify everything via API and dig commands

### Time Estimate
- API automation (all steps): 30-45 minutes
- Verification: 15 minutes
- **Total: 45-60 minutes per domain**

---

## Quick Fix Scripts

### Restore DNS Records
```bash
# Located at: /opt/mailcow-dockerized/restore-dns-gandi.sh
./restore-dns-gandi.sh keken.nu $GANDI_TOKEN
```

### Verify Complete Setup
```bash
# Located at: /opt/mailcow-dockerized/verify-gandi-dns.sh
./verify-gandi-dns.sh keken.nu $GANDI_TOKEN
```

---

## Support Resources

- DNSSEC Solution: `GANDI-DNSSEC-API-COMPLETE-SOLUTION.md`
- Full Report: `GANDI-DNS-MIGRATION-REPORT.md`
- Gandi API Docs: https://api.gandi.net/docs/
- Domain API: https://api.gandi.net/docs/domains/
- LiveDNS API: https://api.gandi.net/docs/livedns/

---

**Last Updated:** 2026-02-21
**Domain Tested:** keken.nu
**Automation Level:** 100% (zero manual steps)
