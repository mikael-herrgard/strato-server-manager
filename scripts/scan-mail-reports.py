#!/usr/bin/env python3
"""
Scan a Mailcow mailbox for DMARC and TLS-RPT (RFC 8460) reports, summarize
them, optionally move processed messages to a Processed folder, and optionally
purge old messages from that folder.

Designed to be invoked from weekly-summary.sh with --format html, but also
runnable standalone for ad-hoc inspection.
"""
import argparse
import email
import email.utils
import gzip
import io
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from email import policy

DOVECOT_CONTAINER = "mailcowdockerized-dovecot-mailcow-1"
DEFAULT_USER = "postmaster@villaherrgard.com"

TLSRPT_CONTENT_TYPES = {"application/tlsrpt+json", "application/tlsrpt+gzip"}
DMARC_HINT_CONTENT_TYPES = {
    "application/zip", "application/gzip", "application/x-gzip",
    "application/xml", "text/xml",
}


# ── Detection ────────────────────────────────────────────────────────────────

def is_tlsrpt_part(part):
    ctype = part.get_content_type()
    if ctype in TLSRPT_CONTENT_TYPES:
        return True
    fn = (part.get_filename() or "").lower()
    if fn.endswith(".json.gz") or fn.endswith(".json"):
        return True
    return False


def is_dmarc_part(part):
    ctype = part.get_content_type()
    fn = (part.get_filename() or "").lower()
    if ctype in DMARC_HINT_CONTENT_TYPES:
        return True
    if fn.endswith(".xml.gz") or fn.endswith(".xml") or fn.endswith(".zip"):
        return True
    return False


# ── Decoding ─────────────────────────────────────────────────────────────────

def decode_payload(part):
    """Get the bytes from a MIME part, transparently decompressing gzip and zip."""
    raw = part.get_payload(decode=True) or b""
    ctype = part.get_content_type()
    fn = (part.get_filename() or "").lower()

    if ctype.endswith("+gzip") or ctype in {"application/gzip", "application/x-gzip"} or fn.endswith(".gz"):
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    elif ctype == "application/zip" or fn.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                names = z.namelist()
                if names:
                    raw = z.read(names[0])
        except (zipfile.BadZipFile, KeyError):
            pass
    return raw


# ── Parsers ──────────────────────────────────────────────────────────────────

def parse_tlsrpt(raw):
    try:
        doc = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    doc["__type__"] = "tlsrpt"
    return doc


def parse_dmarc(raw):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None

    metadata = root.find("report_metadata")
    if metadata is None:
        return None

    org = (metadata.findtext("org_name") or "?").strip()
    report_id = (metadata.findtext("report_id") or "?").strip()

    dr = metadata.find("date_range")
    begin = end = None
    if dr is not None:
        try:
            begin = datetime.fromtimestamp(int(dr.findtext("begin") or 0), tz=timezone.utc)
            end = datetime.fromtimestamp(int(dr.findtext("end") or 0), tz=timezone.utc)
        except (TypeError, ValueError):
            pass

    pp = root.find("policy_published")
    domain = (pp.findtext("domain") if pp is not None else "?") or "?"

    records = []
    for rec in root.findall("record"):
        row = rec.find("row")
        if row is None:
            continue
        try:
            count = int(row.findtext("count") or "0")
        except ValueError:
            count = 0
        pe = row.find("policy_evaluated")
        disposition = (pe.findtext("disposition") if pe is not None else "none") or "none"
        dkim_aligned = (pe.findtext("dkim") if pe is not None else "?") or "?"
        spf_aligned = (pe.findtext("spf") if pe is not None else "?") or "?"
        records.append({
            "count": count,
            "disposition": disposition,
            "dkim_aligned": dkim_aligned,
            "spf_aligned": spf_aligned,
        })

    return {
        "__type__": "dmarc",
        "org": org,
        "report_id": report_id,
        "begin": begin,
        "end": end,
        "domain": domain,
        "records": records,
    }


def parse_message_bytes(raw_bytes, uid=None):
    """Return dict with parsed reports, or None if no reports found.

    Mailcow encrypts Maildir at rest, so we go through doveadm rather than
    reading files directly. raw_bytes is the decrypted RFC 822 message.
    """
    try:
        msg = email.message_from_bytes(raw_bytes, policy=policy.default)
    except (ValueError, TypeError):
        return None

    parsed = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        if is_tlsrpt_part(part):
            doc = parse_tlsrpt(decode_payload(part))
            if doc:
                parsed.append(doc)
                continue
        if is_dmarc_part(part):
            doc = parse_dmarc(decode_payload(part))
            if doc:
                parsed.append(doc)

    if not parsed:
        return None

    msg_id = (msg.get("message-id") or "").strip().strip("<>").strip()
    msg_date_str = msg.get("date") or ""
    try:
        msg_date = email.utils.parsedate_to_datetime(msg_date_str)
    except (TypeError, ValueError):
        msg_date = None

    return {
        "uid": uid,
        "message_id": msg_id,
        "date": msg_date,
        "from": msg.get("from", ""),
        "subject": msg.get("subject", ""),
        "reports": parsed,
    }


# ── doveadm fetcher ──────────────────────────────────────────────────────────

def fetch_inbox_messages(user, days):
    """Yield (uid, raw_bytes) tuples for INBOX messages saved within last `days` days.

    Mailcow encrypts the Maildir at rest, so we ask Dovecot to give us the
    decrypted RFC 822 source via doveadm fetch. doveadm separates messages
    with a form-feed character (\\f).
    """
    try:
        result = subprocess.run(
            ["docker", "exec", DOVECOT_CONTAINER,
             "doveadm", "fetch", "-u", user,
             "uid text", "mailbox", "INBOX", "savedsince", f"{days}d"],
            check=True, capture_output=True, timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        sys.stderr.write(f"doveadm fetch failed: {e}\n")
        return

    raw = result.stdout
    if not raw:
        return

    # doveadm fetch output: one record per message, separated by \f\n
    for record in raw.split(b"\x0c\n"):
        record = record.strip(b"\n")
        if not record:
            continue
        # Each record starts with "uid: <N>\ntext:\n<message bytes>"
        try:
            head, _, body = record.partition(b"text:\n")
        except ValueError:
            continue
        if not body:
            continue
        uid = None
        for line in head.split(b"\n"):
            if line.startswith(b"uid: "):
                try:
                    uid = int(line[5:].decode().strip())
                except ValueError:
                    pass
                break
        yield uid, body


# ── doveadm wrappers ─────────────────────────────────────────────────────────

def doveadm_move(user, uids):
    """Move messages from INBOX to Processed by UID. Returns count moved."""
    moved = 0
    for uid in uids:
        if uid is None:
            continue
        try:
            subprocess.run(
                ["docker", "exec", DOVECOT_CONTAINER,
                 "doveadm", "move", "-u", user,
                 "Processed", "mailbox", "INBOX", "uid", str(uid)],
                check=True, capture_output=True, timeout=10,
            )
            moved += 1
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    return moved


def doveadm_purge(user, days):
    """Expunge messages from Processed older than `days` days. Returns count purged."""
    try:
        result = subprocess.run(
            ["docker", "exec", DOVECOT_CONTAINER,
             "doveadm", "expunge", "-u", user,
             "mailbox", "Processed", "savedbefore", f"{days}d"],
            check=True, capture_output=True, timeout=30,
        )
        # doveadm prints one Info: expunge: line per message
        return result.stderr.decode().count("expunge:") + result.stdout.decode().count("expunge:")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return 0


# ── Aggregation ──────────────────────────────────────────────────────────────

def aggregate(matches, want_tlsrpt=True, want_dmarc=True):
    """Roll matches up into stats dict for rendering."""
    tls_reports = [r for m in matches for r in m["reports"] if r["__type__"] == "tlsrpt"]
    dmarc_reports = [r for m in matches for r in m["reports"] if r["__type__"] == "dmarc"]

    tls_success = 0
    tls_fail = 0
    tls_failure_breakdown = {}
    for r in tls_reports:
        for p in r.get("policies", []):
            s = p.get("summary", {})
            tls_success += s.get("total-successful-session-count", 0)
            tls_fail += s.get("total-failure-session-count", 0)
            for fd in p.get("failure-details", []):
                ft = fd.get("result-type", "?")
                tls_failure_breakdown[ft] = (
                    tls_failure_breakdown.get(ft, 0)
                    + fd.get("failed-session-count", 0)
                )

    dmarc_total = 0
    dmarc_disp = {"none": 0, "quarantine": 0, "reject": 0}
    dmarc_align_fail = 0
    dmarc_per_domain = {}
    for r in dmarc_reports:
        dom = r.get("domain", "?")
        per = dmarc_per_domain.setdefault(dom, {"reports": 0, "messages": 0, "fails": 0})
        per["reports"] += 1
        for rec in r.get("records", []):
            count = rec["count"]
            dmarc_total += count
            per["messages"] += count
            disp = rec.get("disposition", "none")
            dmarc_disp[disp] = dmarc_disp.get(disp, 0) + count
            # Alignment failure = neither DKIM nor SPF passed *with alignment*
            if rec.get("dkim_aligned") != "pass" and rec.get("spf_aligned") != "pass":
                dmarc_align_fail += count
                per["fails"] += count

    return {
        "tls_reports_count": len(tls_reports),
        "tls_success": tls_success,
        "tls_fail": tls_fail,
        "tls_failure_breakdown": tls_failure_breakdown,
        "dmarc_reports_count": len(dmarc_reports),
        "dmarc_total": dmarc_total,
        "dmarc_disp": dmarc_disp,
        "dmarc_align_fail": dmarc_align_fail,
        "dmarc_per_domain": dmarc_per_domain,
    }


def status_for(stats):
    """Return status_class one of: ok, warn, error."""
    if (stats["tls_fail"] > 10
            or stats["dmarc_align_fail"] > 10
            or stats["dmarc_disp"].get("reject", 0) > 0):
        return "error"
    if stats["tls_fail"] > 0 or stats["dmarc_align_fail"] > 0:
        return "warn"
    return "ok"


# ── Rendering ────────────────────────────────────────────────────────────────

def render_text(matches, stats, days):
    print(f"Mail-report scan over last {days} days")
    print(f"Messages with reports found: {len(matches)}")
    print()
    print(f"TLS-RPT reports:   {stats['tls_reports_count']}")
    if stats['tls_reports_count']:
        print(f"  Successful sessions: {stats['tls_success']}")
        print(f"  Failed sessions:     {stats['tls_fail']}")
        for ft, n in sorted(stats['tls_failure_breakdown'].items(), key=lambda x: -x[1]):
            print(f"    {ft}: {n}")
    print()
    print(f"DMARC reports:     {stats['dmarc_reports_count']}")
    if stats['dmarc_reports_count']:
        print(f"  Total messages reported: {stats['dmarc_total']}")
        d = stats['dmarc_disp']
        print(f"  Dispositions: none={d.get('none',0)}, quarantine={d.get('quarantine',0)}, reject={d.get('reject',0)}")
        print(f"  Alignment failures: {stats['dmarc_align_fail']}")
        if stats['dmarc_per_domain']:
            print(f"  Per-domain:")
            for dom, v in sorted(stats['dmarc_per_domain'].items()):
                print(f"    {dom:30s} reports={v['reports']:<3d} messages={v['messages']:<5d} fails={v['fails']}")
    print()
    print(f"Overall status: {status_for(stats).upper()}")


def render_html(matches, stats, days):
    """HTML matching weekly-summary.sh style. STATUS comment is parsed by the bash side."""
    status_cls = status_for(stats)
    out = []
    out.append(f"<!-- STATUS={status_cls} -->")
    out.append(f"<h2>Mail Reports ({days}d)</h2>")

    out.append('<h3 style="margin-top:14px;font-size:13px;color:#2c3e50;">TLS-RPT</h3>')
    out.append("<table>")
    out.append(f'<tr><td class="label">Reports received</td><td class="value">{stats["tls_reports_count"]}</td></tr>')
    if stats['tls_reports_count']:
        out.append(f'<tr><td class="label">Successful sessions</td><td class="value">{stats["tls_success"]}</td></tr>')
        cls = "error" if stats['tls_fail'] > 10 else ("warn" if stats['tls_fail'] > 0 else "ok")
        out.append(f'<tr><td class="label">Failed sessions</td><td class="value {cls}">{stats["tls_fail"]}</td></tr>')
        for ft, n in sorted(stats['tls_failure_breakdown'].items(), key=lambda x: -x[1]):
            out.append(f'<tr><td class="label">  {ft}</td><td class="value">{n}</td></tr>')
    else:
        out.append('<tr><td class="label">Status</td><td class="value">No reports this week (informational)</td></tr>')
    out.append("</table>")

    out.append('<h3 style="margin-top:14px;font-size:13px;color:#2c3e50;">DMARC</h3>')
    out.append("<table>")
    out.append(f'<tr><td class="label">Reports received</td><td class="value">{stats["dmarc_reports_count"]}</td></tr>')
    if stats['dmarc_reports_count']:
        out.append(f'<tr><td class="label">Total messages reported</td><td class="value">{stats["dmarc_total"]}</td></tr>')
        d = stats['dmarc_disp']
        cls = "error" if d.get('reject', 0) > 0 else "ok"
        out.append(f'<tr><td class="label">Dispositions</td><td class="value {cls}">none={d.get("none",0)}, quarantine={d.get("quarantine",0)}, reject={d.get("reject",0)}</td></tr>')
        cls = "error" if stats['dmarc_align_fail'] > 10 else ("warn" if stats['dmarc_align_fail'] > 0 else "ok")
        out.append(f'<tr><td class="label">Alignment failures</td><td class="value {cls}">{stats["dmarc_align_fail"]}</td></tr>')
    else:
        out.append('<tr><td class="label">Status</td><td class="value">No reports this week (informational)</td></tr>')
    out.append("</table>")

    if stats['dmarc_per_domain']:
        out.append('<table style="margin-top:6px;">')
        out.append("<tr><th>Domain</th><th>Reports</th><th>Messages</th><th>Align fails</th></tr>")
        for dom in sorted(stats['dmarc_per_domain']):
            v = stats['dmarc_per_domain'][dom]
            cls = "warn" if v['fails'] > 0 else ""
            out.append(f'<tr><td>{dom}</td><td>{v["reports"]}</td><td>{v["messages"]}</td><td class="{cls}">{v["fails"]}</td></tr>')
        out.append("</table>")

    print("\n".join(out))


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Scan Mailcow mailbox for DMARC and TLS-RPT reports.")
    ap.add_argument("--days", type=int, default=7,
                    help="Look back N days (default 7).")
    ap.add_argument("--user", default=DEFAULT_USER,
                    help=f"Mailbox to scan (default {DEFAULT_USER}).")
    ap.add_argument("--type", choices=["tlsrpt", "dmarc", "both"], default="both",
                    help="Which report types to include.")
    ap.add_argument("--format", choices=["text", "html"], default="text",
                    help="Output format.")
    ap.add_argument("--move-processed", action="store_true",
                    help="Move parsed messages to INBOX/Processed via doveadm.")
    ap.add_argument("--purge-older-than", type=int, default=0,
                    help="Expunge from Processed/ messages older than N days (0 = skip).")
    ap.add_argument("--show-paths", action="store_true",
                    help="Include UIDs and message-ids in text output (was: Maildir paths).")
    args = ap.parse_args()

    matches = []
    for uid, raw_bytes in fetch_inbox_messages(args.user, args.days):
        result = parse_message_bytes(raw_bytes, uid=uid)
        if not result:
            continue
        if args.type != "both":
            result["reports"] = [r for r in result["reports"] if r["__type__"] == args.type]
            if not result["reports"]:
                continue
        matches.append(result)

    stats = aggregate(matches)

    if args.format == "html":
        render_html(matches, stats, args.days)
    else:
        render_text(matches, stats, args.days)
        if args.show_paths:
            print()
            for m in matches:
                print(f"  uid={m['uid']}  msg-id={m['message_id']}  subject={m['subject'][:60]}")

    moved = 0
    if args.move_processed and matches:
        uids = [m["uid"] for m in matches if m["uid"] is not None]
        moved = doveadm_move(args.user, uids)
        sys.stderr.write(f"moved {moved} message(s) to Processed\n")

    purged = 0
    if args.purge_older_than > 0:
        purged = doveadm_purge(args.user, args.purge_older_than)
        sys.stderr.write(f"purged {purged} message(s) from Processed (>{args.purge_older_than}d)\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
