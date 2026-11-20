#!/usr/bin/env bash
# Append a well-formed row to a show-me-your-work decision log (TSV).
# Usage: log.sh <logfile> <phase> <decision> <why> <evidence> <result>
#        log.sh --check <logfile>
set -euo pipefail

header='ts	phase	decision	why	evidence	result'

usage() {
	printf 'usage: log.sh <logfile> <phase> <decision> <why> <evidence> <result>\n       log.sh --check <logfile>\n' >&2
	exit 1
}

# --check: the header, then rows of six non-empty cells with a UTC ts.
# Prints each bad line as <logfile>:<n>: <reason> and exits 1 if any.
# A repeated header line is allowed (see the `>>` note below).
if [ "${1:-}" = "--check" ]; then
	[ "$#" -eq 2 ] || usage
	if [ ! -s "$2" ]; then
		printf '%s: missing or empty\n' "$2" >&2
		exit 1
	fi
	exec awk -F'\t' -v header="$header" -v file="$2" '
		function bad(why) { printf "%s:%d: %s\n", file, NR, why > "/dev/stderr"; failed = 1 }
		NR == 1 { if ($0 != header) bad("header is not: " header); next }
		$0 == header { next }
		NF != 6 { bad(NF " cells, want 6"); next }
		{
			for (i = 1; i <= 6; i++) if ($i ~ /^ *$/) { bad("empty cell " i); next }
			if ($1 !~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z$/)
				bad("ts is not UTC YYYY-MM-DDTHH:MM:SSZ: " $1)
		}
		END { exit failed }
	' "$2"
fi

[ "$#" -eq 6 ] || usage

logfile="$1"
shift

# Refuse an empty cell before writing anything: --check rejects it.
names=(phase decision why evidence result)
for i in 1 2 3 4 5; do
	if [ -z "$(printf '%s' "${!i}" | tr -d ' \t\n\r')" ]; then
		printf 'log.sh: %s is empty\n' "${names[i - 1]}" >&2
		exit 1
	fi
done

logdir="$(dirname "$logfile")"
if [ -n "$logdir" ] && [ "$logdir" != "." ] && [ ! -d "$logdir" ]; then
	mkdir -p "$logdir"
fi

# Use `>>` here, never `>`. A network mount can fail this test for a log
# that exists. Then the cost is one stray header line, not the rows.
if [ ! -s "$logfile" ]; then
	printf '%s\n' "$header" >> "$logfile"
fi

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# Strip tabs/newlines/CR so cells stay on one line, and prefix any cell
# whose first char a spreadsheet would parse as a formula (=, +, -, @)
# with a single quote. The skill expects this log to be read in
# spreadsheets, so attacker-controlled evidence (PR titles, filenames,
# generated text) must not become formula execution when a reviewer
# opens the file.
clean() {
	local v
	v=$(printf '%s' "$1" | tr '\t\n\r' '   ')
	case "$v" in
		=*|+*|-*|@*) printf "'%s" "$v" ;;
		*) printf '%s' "$v" ;;
	esac
}
printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
	"$ts" "$(clean "$1")" "$(clean "$2")" "$(clean "$3")" "$(clean "$4")" "$(clean "$5")" \
	>> "$logfile"
