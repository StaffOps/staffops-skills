#!/usr/bin/env bash
# Shell Text Processing — awk / sed / grep recipes

# ═══ GREP ══════════════════════════════════════════════════════
grep -r "pattern" .                      # recursive search
grep -rn "pattern" --include="*.yaml" .  # with line numbers + filter
grep -rl "old" . | xargs sed -i 's/old/new/g'  # find & replace
grep -E "error|warn|crit" /var/log/syslog       # extended regex (OR)
grep -v "^#\|^$" config.yaml            # strip comments + blanks
grep -c "pattern" file                   # count matches
grep -A3 -B1 "ERROR" app.log           # context: 3 after, 1 before
grep -P '\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}' file  # IP addresses (PCRE)
grep -oP '(?<=token=)[^&]+' url.log    # extract token value (lookahead)

# ═══ SED ═══════════════════════════════════════════════════════
sed 's/old/new/' file                    # first occurrence per line
sed 's/old/new/g' file                   # all occurrences
sed -i 's/old/new/g' file               # in-place edit
sed -i.bak 's/old/new/g' file           # in-place with backup
sed -n '10,20p' file                    # print lines 10-20
sed '/^$/d' file                        # delete empty lines
sed '/^#/d' file                        # delete comment lines
sed 's/[[:space:]]*$//' file            # trim trailing whitespace
sed -n '/START/,/END/p' file            # print between markers
sed 's/\(.*\)=\(.*\)/export \1="\2"/' file  # convert KEY=val to export

# Multi-command
sed -e 's/foo/bar/g' -e 's/baz/qux/g' file
# or with semicolons:
sed 's/foo/bar/g; s/baz/qux/g' file

# Insert/append
sed '3i\New line before line 3' file    # insert before line 3
sed '3a\New line after line 3' file     # append after line 3
sed '$ a\Last line' file                # append at end

# ═══ AWK ═══════════════════════════════════════════════════════
awk '{print $1, $3}' file               # print columns 1 and 3
awk -F: '{print $1}' /etc/passwd        # custom delimiter
awk '/ERROR/ {print}' app.log           # filter lines (like grep)
awk '{sum += $1} END {print sum}' file  # sum a column
awk '{sum += $1; n++} END {print sum/n}' file  # average
awk 'NR==5,NR==10' file                 # lines 5-10
awk '!seen[$0]++' file                  # deduplicate (preserves order)
awk '{print NF}' file                   # count fields per line
awk 'length > 80' file                  # lines longer than 80 chars
awk 'BEGIN{OFS=","} {$1=$1; print}' file  # convert spaces to CSV

# Real-world examples:
# Top 10 IPs from access log
awk '{print $1}' access.log | sort | uniq -c | sort -rn | head -10

# Sum request times (field $NF = last field)
awk '{sum+=$NF} END {printf "Total: %.2fs, Avg: %.3fs\n", sum, sum/NR}' times.log

# Parse key=value pairs
awk -F= '/^DB_HOST/ {print $2}' .env

# ═══ CUT / PASTE / TR / SORT / UNIQ ═══════════════════════════
cut -d: -f1,7 /etc/passwd               # fields 1,7 with : delimiter
cut -c1-10 file                          # first 10 chars per line
paste file1 file2                        # merge files side by side
tr 'a-z' 'A-Z' < file                   # uppercase
tr -d '\r' < win.txt > unix.txt         # remove Windows CR
tr -s ' ' < file                        # squeeze repeated spaces
sort -t: -k3 -n /etc/passwd             # sort by numeric field 3
sort -u file                             # sort + deduplicate
uniq -c | sort -rn                      # count + rank

# ═══ JQ (JSON processing) ═══════════════════════════════════════
cat data.json | jq '.items[].name'       # extract field from array
jq -r '.results[] | "\(.name)\t\(.status)"' data.json  # TSV output
jq 'select(.status == "error")' data.json  # filter
jq -s 'map(.count) | add' data.json    # sum field across array
curl -s http://api/data | jq '.items | length'  # count items

# ═══ YQ (YAML processing) ═══════════════════════════════════════
yq '.metadata.name' manifest.yaml
yq -i '.spec.replicas = 3' deployment.yaml   # edit in-place
yq eval-all '. as $item ireduce ({}; . * $item)' *.yaml  # merge yamls
