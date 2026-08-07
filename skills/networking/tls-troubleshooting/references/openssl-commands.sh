#!/usr/bin/env bash
# TLS Troubleshooting — openssl commands

# ═══ CHECK REMOTE CERTIFICATE ═══════════════════════════════════
# Show cert chain + expiry
openssl s_client -connect example.com:443 -servername example.com </dev/null 2>/dev/null | openssl x509 -noout -dates -subject -issuer

# Full certificate details
openssl s_client -connect example.com:443 -servername example.com </dev/null 2>/dev/null | openssl x509 -noout -text

# Check expiry only (scripting friendly)
openssl s_client -connect example.com:443 -servername example.com </dev/null 2>/dev/null | openssl x509 -noout -enddate
# output: notAfter=Sep 15 12:00:00 2026 GMT

# Days until expiry
echo | openssl s_client -connect example.com:443 -servername example.com 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2 | xargs -I{} bash -c 'echo $(( ($(date -d "{}" +%s) - $(date +%s)) / 86400 )) days'

# Show full chain
openssl s_client -connect example.com:443 -servername example.com -showcerts </dev/null

# ═══ VERIFY CERT AGAINST CA ═════════════════════════════════════
openssl verify -CAfile ca.crt server.crt
openssl verify -CAfile ca-bundle.crt -untrusted intermediate.crt server.crt

# ═══ CHECK LOCAL CERT FILES ═════════════════════════════════════
openssl x509 -in cert.pem -noout -text                  # read cert
openssl x509 -in cert.pem -noout -dates                 # just dates
openssl x509 -in cert.pem -noout -subject -issuer       # who issued it
openssl x509 -in cert.pem -noout -fingerprint -sha256   # fingerprint

# Check key matches cert
openssl x509 -in cert.pem -noout -modulus | openssl md5
openssl rsa -in key.pem -noout -modulus | openssl md5
# ↑ these MUST match

# Check CSR
openssl req -in request.csr -noout -text

# ═══ TEST TLS CONNECTION ════════════════════════════════════════
# Specific TLS version
openssl s_client -connect example.com:443 -tls1_2
openssl s_client -connect example.com:443 -tls1_3

# Specific cipher
openssl s_client -connect example.com:443 -cipher ECDHE-RSA-AES256-GCM-SHA384

# STARTTLS (SMTP, IMAP, etc)
openssl s_client -connect mail.example.com:587 -starttls smtp
openssl s_client -connect mail.example.com:993 -starttls imap

# Client certificate auth
openssl s_client -connect example.com:443 -cert client.crt -key client.key

# ═══ GENERATE SELF-SIGNED (testing only) ═══════════════════════
openssl req -x509 -newkey rsa:4096 -sha256 -days 365 \
  -nodes -keyout server.key -out server.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

# ═══ COMMON ERRORS & CAUSES ═══════════════════════════════════
# "certificate has expired"
#   → cert past notAfter date. Renew it.
#
# "unable to verify the first certificate"
#   → intermediate cert missing from chain. Server must send full chain.
#
# "certificate verify failed (self-signed)"
#   → CA not trusted. Add CA to trust store or use -CAfile.
#
# "hostname mismatch"
#   → cert CN/SAN doesn't include the hostname you're connecting to.
#   → Check: openssl x509 -in cert.pem -noout -ext subjectAltName
#
# "tlsv1 alert protocol version"
#   → server doesn't support the TLS version you're using.
#
# "no peer certificate available"
#   → server didn't present a cert. Wrong port? Not TLS-enabled?

# ═══ CERT-MANAGER (Kubernetes) ═════════════════════════════════
# Check certificate status:
# kubectl get certificates -A
# kubectl describe certificate <name> -n <ns>
# kubectl get certificaterequest -A
# kubectl get challenges -A   # ACME debugging
