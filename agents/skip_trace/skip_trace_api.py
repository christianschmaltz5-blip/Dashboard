#!/usr/bin/env python3
"""
Person → contacts (Phase 3 of the skip-trace agent) — Kevin Andreson / KW Black Hills

Given a person (name + a mailing/property address, from Phase 1's parcel owner or
Phase 2's LLC members) return their likely phone numbers and emails, via a LICENSED
skip-trace provider. This is the last leg: address → owner → people → CONTACTS.

── Compliance (read before flipping this live) ──────────────────────────────────
Contact data here is regulated. Pulling phones/emails for real-estate prospecting
is a valid use, but ONLY through a licensed provider that enforces DPPA/GLBA
permissible-purpose and TCPA/DNC rules — NEVER by scraping TruePeopleSearch-type
sites (ToS + legal exposure). Scrub against DNC before cold-calling. That is why
this module talks only to a paid API and ships with no scraping fallback.

── Provider choice (why the default is pay-per-hit) ─────────────────────────────
For KW's prospecting volume (~hundreds/mo) a pay-per-hit provider is the right call,
NOT an enterprise subscription:
  • REISkip     ~$0.10–0.15 per match, no monthly minimum   ← default recommendation
  • Tracerfy    ~$0.02 per credit
  • Skip Reach  ~$0.05 per successful match
  • BatchData   rebranded from BatchSkipTracing (2025); now ~$2,000/mo minimum — only
                worth it at very high volume. Implemented here for completeness.
Pick one, drop its key in the environment, set SKIPTRACE_PROVIDER, done.

── Config (no secrets in code — CLAUDE.md rule) ─────────────────────────────────
  export SKIPTRACE_PROVIDER=batchdata        # or 'mock' (default when no key)
  export SKIPTRACE_API_KEY=sk_live_...        # provider API token

── Usage ────────────────────────────────────────────────────────────────────────
  python3 skip_trace_api.py "John Smith" "123 Main St, Rapid City SD 57701"
  python3 skip_trace_api.py --json "Jane Doe" "PO Box 9365, Rapid City SD 57709"
  python3 skip_trace_api.py --demo          # run the mock provider end-to-end

Programmatic:
  from skip_trace_api import trace_person, from_parcel
  contacts = trace_person("John", "Smith", "123 Main St, Rapid City SD")
  contacts = from_parcel(rec)   # rec = a parcel_lookup.lookup() dict

Until a real key is set, everything runs against the MOCK provider so the whole
address→owner→people→contacts pipeline is testable today without spending a cent.
"""

import argparse
import json
import os
import re
import sys

import requests

TIMEOUT = 30
HEADERS = {"User-Agent": "KW Black Hills Skip Trace (Kevin Andreson)"}


# ── Normalized result shape ──────────────────────────────────────────────────
def _empty_result(name, provider, matched=False, note=None):
    return {
        "name": name,
        "matched": matched,
        "provider": provider,
        "phones": [],   # list of {"number","type","dnc"}
        "emails": [],   # list of str
        "note": note,
    }


# ── Provider base ────────────────────────────────────────────────────────────
class Provider:
    """A licensed skip-trace backend. Subclasses implement `trace`."""
    name = "base"
    needs_key = True

    def __init__(self, api_key=None):
        self.api_key = api_key

    def trace(self, first, last, address):
        raise NotImplementedError


class MockProvider(Provider):
    """Deterministic fake data so the pipeline is testable with no key / no spend.
    Clearly fake numbers (555-01xx) so mock output is never mistaken for real."""
    name = "mock"
    needs_key = False

    def trace(self, first, last, address):
        full = " ".join(x for x in [first, last] if x).strip()
        seed = sum(ord(c) for c in (full + (address or "")))
        res = _empty_result(full, self.name, matched=True,
                            note="MOCK data — not real. Set SKIPTRACE_PROVIDER + key to go live.")
        res["phones"] = [
            {"number": f"605-555-{seed % 100:02d}{(seed // 7) % 100:02d}", "type": "mobile", "dnc": False},
            {"number": f"605-555-{(seed // 3) % 100:02d}{(seed // 11) % 100:02d}", "type": "landline", "dnc": True},
        ]
        first_l = (first or "owner").lower()
        last_l = (last or "example").lower()
        res["emails"] = [f"{first_l}.{last_l}@example.com"]
        return res


class BatchDataProvider(Provider):
    """BatchData (formerly BatchSkipTracing) property skip-trace.
    Endpoint + payload per developer.batchdata.com; confirm field names against the
    live docs before production, and watch includeTCPABlacklistedPhones / DNC flags."""
    name = "batchdata"
    ENDPOINT = "https://api.batchdata.com/v1/skiptrace"

    def trace(self, first, last, address):
        full = " ".join(x for x in [first, last] if x).strip()
        payload = {
            "requests": [{
                "name": {"first": first or "", "last": last or ""},
                "propertyAddress": _split_address(address),
            }],
            "options": {"includeTCPABlacklistedPhones": False},
        }
        r = requests.post(
            self.ENDPOINT, json=payload, timeout=TIMEOUT,
            headers={**HEADERS,
                     "Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json",
                     "Accept": "application/json"})
        r.raise_for_status()
        return _parse_batchdata(r.json(), full)


def _parse_batchdata(data, full):
    """Map BatchData's response into the normalized shape. Defensive: the exact
    nesting can shift between API versions, so we probe a few likely paths."""
    res = _empty_result(full, "batchdata")
    persons = (data.get("results", {}).get("persons")
               or data.get("persons")
               or (data.get("results", {}).get("skipTrace") if isinstance(data.get("results"), dict) else None)
               or [])
    if not persons:
        res["note"] = "No match."
        return res
    p = persons[0]
    res["matched"] = True
    for ph in (p.get("phoneNumbers") or p.get("phones") or []):
        num = ph.get("number") or ph.get("phoneNumber")
        if num:
            res["phones"].append({
                "number": num,
                "type": ph.get("type") or ph.get("phoneType"),
                "dnc": bool(ph.get("dnc") or ph.get("tcpa")),
            })
    for em in (p.get("emails") or p.get("emailAddresses") or []):
        addr = em.get("email") if isinstance(em, dict) else em
        if addr:
            res["emails"].append(addr)
    return res


PROVIDERS = {p.name: p for p in (MockProvider, BatchDataProvider)}


# ── Address helpers ──────────────────────────────────────────────────────────
def _split_address(address):
    """Best-effort '123 Main St, Rapid City SD 57701' -> structured parts."""
    if not address:
        return {"street": "", "city": "", "state": "", "zip": ""}
    parts = [p.strip() for p in address.split(",")]
    street = parts[0] if parts else ""
    city = state = zip_ = ""
    tail = " ".join(parts[1:]) if len(parts) > 1 else ""
    m = re.search(r"([A-Za-z .'-]+?)\s+([A-Z]{2})\s*(\d{5}(?:-\d{4})?)?\s*$", tail)
    if m:
        city, state, zip_ = m.group(1).strip(), m.group(2), (m.group(3) or "")
    return {"street": street, "city": city, "state": state, "zip": zip_}


def _split_name(full):
    """'JOHN Q SMITH' -> ('John', 'Smith'). Entities have no person name."""
    toks = [t for t in re.split(r"\s+", (full or "").strip()) if t]
    if not toks:
        return "", ""
    if len(toks) == 1:
        return toks[0].title(), ""
    return toks[0].title(), toks[-1].title()


# ── Public API ───────────────────────────────────────────────────────────────
def _select_provider():
    """Choose a provider from env. Falls back to mock when no key is configured."""
    name = (os.environ.get("SKIPTRACE_PROVIDER") or "").strip().lower()
    key = os.environ.get("SKIPTRACE_API_KEY")
    if not name:
        name = "batchdata" if key else "mock"
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown SKIPTRACE_PROVIDER {name!r}. Options: {', '.join(PROVIDERS)}")
    if cls.needs_key and not key:
        # Configured for a live provider but no key — fail loud rather than silently mock.
        raise RuntimeError(
            f"Provider {name!r} needs SKIPTRACE_API_KEY. Set it, or unset "
            f"SKIPTRACE_PROVIDER to use the mock provider.")
    return cls(api_key=key)


def trace_person(first, last, address):
    """Person + address -> normalized contacts dict (phones, emails, matched...)."""
    return _select_provider().trace(first, last, address)


def from_parcel(rec):
    """Take a Phase-1 parcel_lookup record and trace the owner.

    If the owner is an LLC/trust this needs Phase 2 (SD SoS) first to get the
    people, so we return a note instead of tracing the entity name itself.
    """
    if not rec or not rec.get("owner"):
        return _empty_result("", "n/a", note="No parcel/owner to trace.")
    owner = rec["owner"]
    if rec.get("owner_is_entity"):
        return _empty_result(
            owner, "n/a",
            note="Owner is an LLC/trust — run Phase 2 (SD SoS) to get the people, "
                 "then trace each person.")
    first, last = _split_name(owner)
    address = rec.get("mailing_address") or rec.get("situs_address")
    return trace_person(first, last, address)


# ── Formatting / CLI ─────────────────────────────────────────────────────────
def format_contacts(res):
    lines = [f"PERSON   : {res['name'] or '—'}   (via {res['provider']})"]
    if res.get("note"):
        lines.append(f"NOTE     : {res['note']}")
    if res["phones"]:
        lines.append("PHONES   :")
        for ph in res["phones"]:
            flags = " ".join(f for f in [ph.get("type"), "DNC" if ph.get("dnc") else ""] if f)
            lines.append(f"           {ph['number']}  {flags}".rstrip())
    else:
        lines.append("PHONES   : —")
    lines.append("EMAILS   : " + (", ".join(res["emails"]) if res["emails"] else "—"))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Person + address -> contacts (licensed skip trace)")
    ap.add_argument("name", nargs="?", help='full name, e.g. "John Smith"')
    ap.add_argument("address", nargs="?", help='mailing/property address')
    ap.add_argument("--json", action="store_true", help="output raw JSON")
    ap.add_argument("--demo", action="store_true", help="run the mock provider on sample data")
    args = ap.parse_args()

    if args.demo:
        os.environ.pop("SKIPTRACE_PROVIDER", None)
        os.environ.pop("SKIPTRACE_API_KEY", None)
        res = trace_person("John", "Smith", "123 Main St, Rapid City SD 57701")
        print(format_contacts(res))
        return
    if not args.name:
        ap.error('give a name (and address), or use --demo')

    first, last = _split_name(args.name)
    try:
        res = trace_person(first, last, args.address)
    except (RuntimeError, ValueError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(2)
    except requests.exceptions.RequestException as e:
        print(f"Skip-trace failed (network/API error): {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(format_contacts(res))


if __name__ == "__main__":
    main()
