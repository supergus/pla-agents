#!/usr/bin/env bash
# OWL checks with ROBOT + HermiT. Needs Java 11+ and robot.jar.
# Usage: ROBOT_JAR=/path/to/robot.jar scripts/reason.sh   (default: ./robot.jar)
set -euo pipefail
cd "$(dirname "$0")/.."
ROBOT="java -jar ${ROBOT_JAR:-robot.jar}"
CAT="--catalog ontology/catalog-v001.xml"
mkdir -p build
python scripts/quote.py --ttl build/quote-results.ttl > /dev/null

echo "== 1. OWL 2 DL profile (ontology, then ontology + data)"
$ROBOT merge $CAT -i ontology/rfq.ttl validate-profile --profile DL -o build/profile-ontology.txt
$ROBOT merge $CAT -i build/quote-results.ttl -i data/rfq-1002-incomplete.ttl validate-profile --profile DL -o build/profile-data.txt
head -1 build/profile-ontology.txt build/profile-data.txt

echo "== 2. HermiT: consistency + no unsatisfiable classes (ROBOT exits non-zero otherwise)"
$ROBOT merge $CAT -i ontology/rfq.ttl \
  reason --reasoner hermit --equivalent-classes-allowed asserted-only -o build/rfq-merged.ttl

echo "== 3. ROBOT report (fail on ERROR)"
$ROBOT merge $CAT -i ontology/rfq.ttl report --fail-on ERROR -o build/report.tsv

echo "== 4. HermiT over ontology + example data (consistency, inferred types incl. CompleteRFQ)"
$ROBOT merge $CAT -i build/quote-results.ttl -i data/rfq-1002-incomplete.ttl \
  reason --reasoner hermit --axiom-generators "ClassAssertion" --include-indirect true -o build/reasoned.ttl
echo "OK"
