---
name: tls-troubleshooting
description: "Diagnose certificate chains, expiry and handshake failures."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [tls, ssl, certificate, openssl, handshake, chain, sni]
    category: networking
    related_skills: [network-troubleshooting-tools, tcp-ip-fundamentals]
---
# TLS Troubleshooting

Diagnosing certificate and handshake failures with `openssl s_client` —
expired or wrong certificates, incomplete chains, SNI mismatches, and
protocol/cipher negotiation failures. Most TLS problems are answerable from
one command's output if you know what to look for in it.

## When to Use

Use when a TLS handshake fails, a browser or client reports a certificate
error, a certificate is expiring, or a service works with one client but not
another (often a protocol/cipher support gap).

## openssl s_client — the primary diagnostic

```bash
openssl s_client -connect example.com:443
openssl s_client -connect example.com:443 -servername example.com   # SNI -- almost always needed
```

**Always include `-servername`.** Without it, no SNI (Server Name
Indication) is sent, and a server hosting multiple certificates on the same
IP (essentially all modern TLS termination — load balancers, CDNs, virtual
hosting) will present its *default* certificate rather than the one for the
requested name. This is the single most common cause of "the certificate is
wrong" that turns out to be a testing mistake, not a real misconfiguration.

```bash
openssl s_client -connect example.com:443 -servername example.com </dev/null
```

Appending `</dev/null` closes stdin immediately after the handshake instead
of leaving the command waiting for interactive input — makes it usable in
scripts and avoids an accidental hang.

## Reading the output

```
CONNECTED(00000003)
depth=2 C = US, O = ISRG, CN = ISRG Root X1
verify return:1
depth=1 C = US, O = Let's Encrypt, CN = R3
verify return:1
depth=0 CN = example.com
verify return:1
---
Certificate chain
 0 s:CN = example.com
   i:C = US, O = Let's Encrypt, CN = R3
 1 s:C = US, O = Let's Encrypt, CN = R3
   i:C = US, O = ISRG, CN = ISRG Root X1
---
SSL-Session:
    Protocol  : TLSv1.3
    Cipher    : TLS_AES_256_GCM_SHA384
---
Verify return code: 0 (ok)
```

| Field | What to check |
| --- | --- |
| `verify return:1` at each depth | Each certificate in the chain validated against its issuer |
| `Certificate chain`, entries `0`, `1`, ... | The full chain as presented — `s:` (subject) / `i:` (issuer) |
| `Protocol` | Which TLS version was negotiated |
| `Verify return code` | `0 (ok)` is success; anything else names the specific failure |

`Verify return code: 0 (ok)` is the bottom-line pass/fail signal — everything
above it is context for *why*, when it isn't 0.

## Common verify return codes

| Code | Meaning |
| --- | --- |
| 0 | ok |
| 10 | Certificate has expired |
| 18 | Self-signed certificate |
| 19 | Self-signed certificate in the chain (an intermediate, not the leaf) |
| 20 | Unable to get local issuer certificate — the chain is **incomplete** |
| 21 | Unable to verify the first certificate — related to an incomplete chain |
| 24 | Invalid CA certificate |
| 62 | Hostname mismatch |

**Code 20/21 (incomplete chain) is the most common real-world failure**, and
the confusing part is that browsers often succeed anyway — most browsers
cache intermediate certificates they've seen before and can complete the
chain themselves. A server that omits the intermediate certificate can look
fine in a browser while failing for every other client (curl, most language
HTTP libraries, mobile apps) that doesn't have that cache. Always test with
`openssl s_client`, not just a browser, before declaring a chain correctly
configured.

## Checking expiry

```bash
openssl s_client -connect example.com:443 -servername example.com </dev/null 2>/dev/null \
    | openssl x509 -noout -dates

echo | openssl s_client -connect example.com:443 -servername example.com 2>/dev/null \
    | openssl x509 -noout -subject -issuer -dates
```

```
notBefore=Jan  1 00:00:00 2026 GMT
notAfter=Apr  1 23:59:59 2026 GMT
```

For monitoring/scripting, extract the expiry as a comparable value:

```bash
end_date=$(echo | openssl s_client -connect example.com:443 -servername example.com 2>/dev/null \
    | openssl x509 -noout -enddate | cut -d= -f2)
days_left=$(( ($(date -d "$end_date" +%s) - $(date +%s)) / 86400 ))
echo "$days_left days until expiry"
```

`date -d` is GNU-specific; on macOS/BSD use `date -j -f`. Alert well before
expiry (typically 30/14/7-day thresholds) — certificate expiry is one of the
most preventable classes of outage, entirely avoidable with monitoring.

## Inspecting a certificate directly

```bash
openssl x509 -in cert.pem -noout -text                      # everything: subject, SANs, validity, extensions
openssl x509 -in cert.pem -noout -subject -issuer -dates
openssl x509 -in cert.pem -noout -ext subjectAltName          # Subject Alternative Names -- what hostnames it actually covers
```

Modern clients validate against **SAN** (Subject Alternative Name) entries,
not the legacy Common Name (CN) field. A certificate missing the expected
hostname in its SAN list fails validation even if the CN looks correct —
always check SANs specifically, not just the subject line.

## Testing what a server actually supports

```bash
openssl s_client -connect example.com:443 -tls1_2      # force a specific version
openssl s_client -connect example.com:443 -tls1_3
openssl s_client -connect example.com:443 -cipher 'ECDHE-RSA-AES256-GCM-SHA384'   # a specific cipher

nmap --script ssl-enum-ciphers -p 443 example.com        # enumerate everything supported, if nmap is available
```

"Works from one client, fails from another" is very often a protocol or
cipher mismatch — an old client that only offers TLS 1.0/1.1 against a
server that's disabled them (correctly, for security), or the reverse: a
strict client refusing a server still offering a deprecated protocol.
Forcing a specific version with `-tls1_2` etc. isolates exactly which side
the constraint is on.

## Verifying against a specific CA bundle

```bash
openssl s_client -connect example.com:443 -servername example.com -CAfile /path/to/ca-bundle.pem
curl --cacert /path/to/ca-bundle.pem https://example.com
```

Useful for internal/private CAs where the system's default trust store
doesn't include the issuing CA — confirms whether a failure is "the
certificate is genuinely invalid" versus "this specific client doesn't trust
this specific CA," which have very different fixes.

## Mutual TLS (client certificates)

```bash
openssl s_client -connect example.com:443 -servername example.com \
    -cert client.pem -key client-key.pem
```

A server requesting a client certificate but receiving none (or an
untrusted one) typically fails the handshake or accepts the connection but
rejects the application-level request — the distinction matters for
diagnosis. Check the server's logs for which stage actually rejected it, not
just the client-side error.

## Pitfalls

- **Omitting `-servername`** — the server presents its default certificate
  for the IP instead of the one for the actual hostname; the most common
  false "wrong certificate" report.
- **Trusting a browser's success as proof the chain is complete** —
  browsers cache intermediates and can mask an incomplete chain that other
  clients will fail on.
- **Checking CN instead of SAN** — modern validation uses SAN; CN alone is
  legacy and often absent or misleading.
- **Assuming an expired certificate is the only possible cause of a
  handshake failure** — `Verify return code` names the actual reason;
  read it before guessing.
- **Not testing with `</dev/null`** — an interactive `s_client` session left
  open looks like a hang in a script or CI job.
- **Skipping protocol/cipher isolation** — "works for some clients, not
  others" needs `-tls1_2`/`-tls1_3`/`-cipher` testing to pin down, not
  assumptions.

## Reference

- `network-troubleshooting-tools` — `curl -v`, `tcpdump`, and where TLS
  failure fits into a broader connection diagnosis
- `tcp-ip-fundamentals` — confirming the TCP handshake completes before
  blaming a hang on TLS
